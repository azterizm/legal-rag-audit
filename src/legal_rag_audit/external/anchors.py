"""Point-in-time anchors — the external, public half of the ground truth (§9.2, F27).

The planted battery mints its own answers, so its ground truth is ours by construction.
This one cannot: the answer to *"what was the qualifying period for unfair dismissal on
1 January 2011"* is a fact about the law, and the only defensible ground truth for it is
the primary source. So an anchor records a **provision, a date, and the short phrase that
identifies the version in force on that date** — quoted verbatim from
`legislation.gov.uk`, which publishes under the Open Government Licence.

**Why a phrase and not the provision.** Every Tier 1 check in this tool is *"did this
exact string appear"*, and that rule does not change because the source is external. A
whole provision would have to be matched by similarity, which needs a model and would put
this check in Tier 2 — where the finding becomes contestable on our threshold rather than
on the law. A phrase chosen so that it appears in one version and in no other keeps the
check exact, and keeps it checkable by hand by anyone holding the same two URLs.

**What makes a phrase usable, and why the set is this small.** Three rules, and every
candidate that fails one is left out rather than weakened:

1. *Discriminating.* It must appear in this version and in no other version of the same
   provision. `30-day period` is in both the pre- and post-2015 forms of the Late Payment
   of Commercial Debts (Interest) Act 1998 s.4, so that instrument is absent here despite
   being the obvious commercial-contracts anchor — §20.1 item 3 asks for one and this
   file does not yet have one that meets rule 1.
2. *Not reachable by paraphrase of the other version.* A system correctly describing the
   2014 form of a provision must not emit the 2015 form's phrase by accident. This is the
   rule that rejects most candidates: `agreed payment day` is the post-2015 defined term,
   and a paraphrase of the pre-2015 wording — which says the parties may *agree a date for
   payment* — lands on it without the system doing anything wrong. §14.2 makes a false
   positive a release blocker, so a phrase that can be reached innocently is not a phrase.
3. *Stable.* Prefer a pair of dates that are both historic, because a historic version can
   never change again. `era-124` is that pattern deliberately: both readings sit in closed
   validity ranges, so the anchor needs no maintenance ever. `era-108`'s second reading is
   the law as it stands, which is the more natural question and the one that can go stale —
   `ingest --verify` is what catches it, and the two anchors together are the argument for
   why that command exists.

> [!IMPORTANT]
> Nothing here is planted, and nothing here is uploaded. This is the half of §9.1 that
> runs against the target's own index with **no `upload` endpoint at all** (F25), which is
> also what makes it the half that cannot be dismissed as synthetic.
"""

from dataclasses import dataclass
from typing import Final, Optional

#: legislation.gov.uk publishes under the Open Government Licence v3.0, which permits
#: copying and adaptation with attribution. Recorded on every anchor rather than in a
#: footnote: the phrases below are quoted from Crown copyright material, and a tool that
#: takes provenance this seriously about its own output should say where its inputs came
#: from in the same structure that carries them.
OGL: Final = (
    "Contains public sector information licensed under the Open Government Licence v3.0"
)

BASE: Final = "https://www.legislation.gov.uk"


@dataclass(frozen=True)
class Reading:
    """One provision as it stood at one moment, and the question that asks for it."""

    #: ISO date the question asks about. `None` asks for the law as it stands, which is
    #: the more natural question and the one that can go stale.
    as_at: Optional[str]
    question: str
    #: The discriminating phrase, verbatim from the source. See the three rules above.
    invariant: str
    #: The validity range legislation.gov.uk states for this version. `in_force_to` of
    #: `None` means the version is current — the only kind that can move under us.
    in_force_from: str
    in_force_to: Optional[str] = None

    @property
    def frozen(self) -> bool:
        """Whether this reading can ever change. A closed range cannot."""
        return self.in_force_to is not None


@dataclass(frozen=True)
class Anchor:
    """A provision and two readings of it. **The pair is the test.**

    A single dated question measures almost nothing: a system that always answers with
    the current law passes every question about the present. Asking the same provision at
    two moments is what separates *retrieved the right version* from *only has one*.
    """

    anchor_id: str
    #: legislation.gov.uk path, e.g. `ukpga/1996/18`.
    instrument: str
    title: str
    section: str
    #: What a correct answer has to name. Used by the `version_mismatch` counter: an
    #: answer that identifies the provision correctly and then quotes the superseded text
    #: is worse than one that does neither, because it reads as authoritative.
    provision: str
    topic: str
    readings: tuple[Reading, Reading]
    licence: str = OGL

    def url(self, reading: Reading) -> str:
        stem = f"{BASE}/{self.instrument}/section/{self.section}"
        return stem if reading.as_at is None else f"{stem}/{reading.as_at}"


ANCHORS: Final[tuple[Anchor, ...]] = (
    Anchor(
        anchor_id="era-108",
        instrument="ukpga/1996/18",
        title="Employment Rights Act 1996",
        section="108",
        provision="section 108",
        topic="employment",
        readings=(
            Reading(
                as_at="2011-01-01",
                question=(
                    "As at 1 January 2011, how long did an employee have to have been "
                    "continuously employed before section 94 of the Employment Rights "
                    "Act 1996 applied to their dismissal?"
                ),
                invariant="not less than one year",
                in_force_from="2010-10-01",
                in_force_to="2011-04-06",
            ),
            Reading(
                as_at=None,
                question=(
                    "How long must an employee have been continuously employed before "
                    "section 94 of the Employment Rights Act 1996 applies to their "
                    "dismissal?"
                ),
                invariant="not less than two years",
                in_force_from="2012-04-06",
                # Live. The qualifying period is under active legislative attention, and
                # this is the reading `ingest --verify` exists to re-check.
                in_force_to=None,
            ),
        ),
    ),
    Anchor(
        anchor_id="era-124",
        instrument="ukpga/1996/18",
        title="Employment Rights Act 1996",
        section="124",
        provision="section 124",
        topic="employment",
        # Both readings historic, both validity ranges closed. This anchor is finished:
        # no refresh can change either answer, which is the pattern to copy.
        readings=(
            Reading(
                as_at="2012-01-01",
                question=(
                    "As at 1 January 2012, what was the maximum compensatory award for "
                    "unfair dismissal under section 124 of the Employment Rights Act "
                    "1996?"
                ),
                invariant="£68,400",
                in_force_from="2011-02-01",
                in_force_to="2012-02-01",
            ),
            Reading(
                as_at="2014-01-01",
                question=(
                    "As at 1 January 2014, what was the maximum compensatory award for "
                    "unfair dismissal under section 124 of the Employment Rights Act "
                    "1996?"
                ),
                invariant="£74,200",
                in_force_from="2013-07-29",
                in_force_to="2014-04-06",
            ),
        ),
    ),
)

BY_ID: Final[dict[str, Anchor]] = {a.anchor_id: a for a in ANCHORS}


class AnchorError(Exception):
    """The anchor set contradicts itself. A setup problem, not a finding (NF9)."""


def validate_anchors(anchors: tuple[Anchor, ...] = ANCHORS) -> None:
    """Refuse an anchor set that could produce a finding against a correct answer.

    Two rules, both of which have exactly one failure mode and it is a false positive:
    an anchor whose two readings share an invariant scores the same string as required
    and forbidden, and an anchor whose invariant appears in the other reading's question
    would fail a system that did nothing but repeat what it was asked.
    """
    seen: set[str] = set()
    for anchor in anchors:
        if anchor.anchor_id in seen:
            raise AnchorError(f"duplicate anchor id {anchor.anchor_id!r}")
        seen.add(anchor.anchor_id)

        first, second = anchor.readings
        if _norm(first.invariant) == _norm(second.invariant):
            raise AnchorError(
                f"{anchor.anchor_id}: both readings carry the invariant "
                f"{first.invariant!r}.\n"
                f"  The pair is the test, and two readings that cannot be told apart "
                f"test nothing."
            )
        for reading, other in ((first, second), (second, first)):
            if _norm(other.invariant) in _norm(reading.question):
                raise AnchorError(
                    f"{anchor.anchor_id}: the question asked about "
                    f"{reading.as_at or 'the present'} contains the other reading's "
                    f"invariant {other.invariant!r}.\n"
                    f"  A system that echoed the question would be recorded as having "
                    f"returned the wrong version."
                )
            if _norm(reading.invariant) in _norm(reading.question):
                raise AnchorError(
                    f"{anchor.anchor_id}: the question asked about "
                    f"{reading.as_at or 'the present'} already contains its own answer "
                    f"{reading.invariant!r}."
                )


def _norm(text: str) -> str:
    return " ".join((text or "").split()).casefold()
