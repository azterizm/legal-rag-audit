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
   of Commercial Debts (Interest) Act 1998 s.4, which is why that instrument — the obvious
   commercial-contracts candidate — is not here. §20.1 item 3's commercial anchors are
   instead the Companies Act 2006 accounting thresholds, where every version states a
   different figure and rule 1 is satisfied by construction.
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
   `ingest` is what catches it, and the two anchors together are the argument for why that
   command exists. Every anchor added after those two is fully frozen, so exactly one
   reading in this file can ever move.

**A fourth rule, learned by rejecting candidates.** *The figure must have one written
form.* A phrase is scored by exact containment, so an invariant a correct system would
naturally write differently is a false positive waiting to happen — and §14.2 makes a
false positive a release blocker. Rejected on this ground:

* **ERA 1996 s.31** (guarantee payment daily limit), whose readings are `£24.20` and
  `£28.00`. A system that answers *£28* is right, and would be recorded as having
  returned the superseded version. Trailing zeros are not a phrase.
* **Insolvency Act 1986 s.123**, where the £750 statutory-demand threshold is the same at
  every date checked — no pair, so nothing to discriminate (rule 1).
* **Companies Act 2006 s.477**, whose operative text carries no figure at all; the
  thresholds it turns on live in s.382.

The Companies Act anchors below carry `£6.5` rather than `£6.5 million` for the same
reason: a system writing *£6.5m* or *£6.5 million* satisfies the shorter phrase and both
are correct answers. The figure alone is still discriminating — no other version of that
provision states it.

**Where the fourth rule ran out, and what replaced it (defect 23).** It was written about
figures and it holds for figures: `£508` is `£508`, and a shorter prefix absorbs the
variants. It does not hold for a quantity the statute states in *words*. `era-108` reads
*not less than one year*; the second live target answered *at least one year* — the
ordinary English rendering of the same formula, correct on both halves of the pair — and
was recorded as having returned neither version. Under-detection is the safe direction,
but it cost the comparison: the first target committed to the statutory phrase and was
scored on it, and the two runs stopped being comparable on that anchor.

A reading may therefore carry `also_accepted`: other written forms of *the same answer*.
They widen `must_contain` and never `must_not_contain` — see `Reading.accepted` for why
that asymmetry is the entire safety argument — and `validate_anchors` applies every rule
above to the widened set, because a rule enforced on the canonical phrase alone would
have a hole exactly the width of the new feature. Only `invariant` is checked against
the primary source; the alternatives are renderings, and the statute does not contain
them.

The set is not open-ended. Enumerating how a system might *word* an answer is the trap
§8.2 #8 names by hand; enumerating how a fixed quantity is written in English is a closed
set — *not less than*, *at least*, *a minimum of* — and stops there.

**Why the set is employment- and company-law heavy.** These are the provisions whose
amendments are *numeric*. A qualitative amendment gives no phrase that survives rule 2,
which is the constraint that rejects most of the statute book rather than a judgement
about which law matters.

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
    #: This is the only form `ingest --verify` checks against `legislation.gov.uk`,
    #: because it is the only one the source contains.
    invariant: str
    #: The validity range legislation.gov.uk states for this version. `in_force_to` of
    #: `None` means the version is current — the only kind that can move under us.
    in_force_from: str
    in_force_to: Optional[str] = None
    #: Other written forms of **the same answer** — defect 23. See `accepted`.
    also_accepted: tuple[str, ...] = ()

    @property
    def frozen(self) -> bool:
        """Whether this reading can ever change. A closed range cannot."""
        return self.in_force_to is not None

    @property
    def accepted(self) -> tuple[str, ...]:
        """Every written form that counts as having returned this version.

        The fourth rule — *the figure must have one written form* — was written about
        figures and holds for figures: `£508` is `£508`. It does not hold for a
        quantity the statute states in words. `era-108` reads *not less than one year*,
        and a system that answers *at least one year* has returned the right version of
        the law in the ordinary English rendering of that formula.

        The second live target did exactly that, on both halves of the pair, and scored
        as having returned neither version (defect 23). Under-detection is the safe
        direction — §14.2 makes a false positive the release blocker and a missed one
        merely a cost — but the cost was not nothing: the first target committed to the
        statutory phrase and was scored on it, this one paraphrased and was scored on
        nothing, and the two runs stopped being comparable on that anchor.

        **These forms widen `must_contain` and never `must_not_contain`.** A system that
        says the right thing in other words now passes; a system that says the wrong
        thing still has to produce the superseded phrase verbatim to fail. That
        asymmetry is deliberate and it is the whole safety argument: every form added
        here can only turn a NOT_CAPTURED into a PASS, never a PASS into a finding.

        What it costs, stated rather than hidden: a system that paraphrases the *wrong*
        version escapes the finding and lands in NOT_CAPTURED. That is the same
        under-detection this tool already accepts everywhere else, and the alternative —
        loose forms in `must_not_contain` — buys sensitivity with exactly the failure
        §14.2 refuses.

        Forms are the standard renderings of the statutory formula, not a list of
        phrasings someone might use. Enumerating how a system could word an answer is
        the trap §8.2 #8 names; enumerating how a fixed quantity is written in English
        is a closed set.
        """
        return (self.invariant, *self.also_accepted)


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
                # The three standard renderings of the statutory formula. A system
                # answering *at least one year* has returned this version of the law,
                # and the exact phrase alone recorded that as neither version (defect
                # 23). Every form names its own quantity, so none is reachable from the
                # other reading — `validate_anchors` refuses the set if one is.
                also_accepted=("at least one year", "a minimum of one year"),
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
                also_accepted=("at least two years", "a minimum of two years"),
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
    # ---------------------------------------------------------------- employment
    Anchor(
        anchor_id="era-227",
        instrument="ukpga/1996/18",
        title="Employment Rights Act 1996",
        section="227",
        provision="section 227",
        topic="employment",
        # Uprated every April by an Employment Rights (Increase of Limits) Order, so this
        # provision alone supplies a decade of closed ranges. Two are used; the rest are
        # there if the set ever needs to grow without a new instrument.
        readings=(
            Reading(
                as_at="2014-06-01",
                question=(
                    "As at 1 June 2014, what was the maximum amount of a week's pay for "
                    "calculating a redundancy payment or a basic award under section 227 "
                    "of the Employment Rights Act 1996?"
                ),
                invariant="£464",
                in_force_from="2014-04-06",
                in_force_to="2016-04-06",
            ),
            Reading(
                as_at="2020-06-01",
                question=(
                    "As at 1 June 2020, what was the maximum amount of a week's pay for "
                    "calculating a redundancy payment or a basic award under section 227 "
                    "of the Employment Rights Act 1996?"
                ),
                invariant="£538",
                in_force_from="2020-04-06",
                in_force_to="2021-04-06",
            ),
        ),
    ),
    Anchor(
        anchor_id="era-186",
        instrument="ukpga/1996/18",
        title="Employment Rights Act 1996",
        section="186",
        provision="section 186",
        topic="employment",
        readings=(
            Reading(
                as_at="2014-01-01",
                question=(
                    "As at 1 January 2014, what was the weekly limit on a debt payable "
                    "by the Secretary of State to an employee of an insolvent employer "
                    "under section 186 of the Employment Rights Act 1996?"
                ),
                invariant="£450",
                in_force_from="2013-02-01",
                in_force_to="2014-04-06",
            ),
            Reading(
                as_at="2019-01-01",
                question=(
                    "As at 1 January 2019, what was the weekly limit on a debt payable "
                    "by the Secretary of State to an employee of an insolvent employer "
                    "under section 186 of the Employment Rights Act 1996?"
                ),
                invariant="£508",
                in_force_from="2018-04-06",
                in_force_to="2019-04-06",
            ),
        ),
    ),
    # ------------------------------------------------------- commercial / company
    #
    # §20.1 item 3, finally answered. Both anchors below are company-law accounting
    # thresholds, chosen because every version of them states a different set of figures:
    # rule 1 holds by construction, and rule 2 cannot fail because a paraphrase of one
    # threshold cannot produce another threshold's number.
    Anchor(
        anchor_id="ca-382",
        instrument="ukpga/2006/46",
        title="Companies Act 2006",
        section="382",
        provision="section 382",
        topic="commercial",
        readings=(
            Reading(
                as_at="2014-01-01",
                question=(
                    "As at 1 January 2014, what was the maximum turnover a company could "
                    "have and still qualify as a small company under section 382 of the "
                    "Companies Act 2006?"
                ),
                invariant="£6.5",
                in_force_from="2008-04-06",
                in_force_to="2016-01-01",
            ),
            Reading(
                as_at="2019-01-01",
                question=(
                    "As at 1 January 2019, what was the maximum turnover a company could "
                    "have and still qualify as a small company under section 382 of the "
                    "Companies Act 2006?"
                ),
                invariant="£10.2",
                in_force_from="2016-01-01",
                in_force_to="2025-04-06",
            ),
        ),
    ),
    Anchor(
        anchor_id="ca-465",
        instrument="ukpga/2006/46",
        title="Companies Act 2006",
        section="465",
        provision="section 465",
        topic="commercial",
        readings=(
            Reading(
                as_at="2014-01-01",
                question=(
                    "As at 1 January 2014, what was the maximum turnover for a company to "
                    "qualify as medium-sized under section 465 of the Companies Act 2006?"
                ),
                invariant="£25.9",
                in_force_from="2008-04-06",
                in_force_to="2016-01-01",
            ),
            Reading(
                as_at="2019-01-01",
                question=(
                    "As at 1 January 2019, what was the maximum turnover for a company to "
                    "qualify as medium-sized under section 465 of the Companies Act 2006?"
                ),
                invariant="£36",
                in_force_from="2016-01-01",
                in_force_to="2025-04-06",
            ),
        ),
    ),
)

BY_ID: Final[dict[str, Anchor]] = {a.anchor_id: a for a in ANCHORS}


class AnchorError(Exception):
    """The anchor set contradicts itself. A setup problem, not a finding (NF9)."""


def validate_anchors(anchors: tuple[Anchor, ...] = ANCHORS) -> None:
    """Refuse an anchor set that could produce a finding against a correct answer.

    Rules, each of which has exactly one failure mode and it is a false positive: an
    anchor whose two readings share an accepted form scores the same string as required
    and forbidden; an anchor whose invariant appears in the other reading's question
    would fail a system that did nothing but repeat what it was asked; and — since
    defect 23 widened a reading to several written forms — an added form that overlaps
    the other reading would make a right answer look like the wrong one.

    Every rule is checked over `reading.accepted`, not over `reading.invariant`. A rule
    enforced on the canonical phrase and not on its alternatives is a rule with a hole
    the exact width of the feature that was just added.
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
            if len({_norm(f) for f in reading.accepted}) != len(reading.accepted):
                raise AnchorError(
                    f"{anchor.anchor_id}: the reading for "
                    f"{reading.as_at or 'the present'} lists the same accepted form "
                    f"twice: {list(reading.accepted)}."
                )
            for form in reading.accepted:
                if not form.strip():
                    raise AnchorError(
                        f"{anchor.anchor_id}: an empty accepted form would match every "
                        f"answer ever given."
                    )
                # The discriminating rule, over the widened set. If one reading's form
                # is contained in the other's, an answer stating one version satisfies
                # both and the pair stops separating anything.
                for rival in other.accepted:
                    if _norm(form) in _norm(rival) or _norm(rival) in _norm(form):
                        raise AnchorError(
                            f"{anchor.anchor_id}: the accepted form {form!r} for "
                            f"{reading.as_at or 'the present'} overlaps {rival!r} from "
                            f"the other reading.\n"
                            f"  One version's answer would satisfy both readings, and "
                            f"the pair would stop\n  telling them apart. Accepted forms "
                            f"must each name their own version's answer."
                        )
                if _norm(form) in _norm(reading.question):
                    raise AnchorError(
                        f"{anchor.anchor_id}: the question asked about "
                        f"{reading.as_at or 'the present'} already contains its own "
                        f"answer {form!r}."
                    )
            for form in other.accepted:
                if _norm(form) in _norm(reading.question):
                    raise AnchorError(
                        f"{anchor.anchor_id}: the question asked about "
                        f"{reading.as_at or 'the present'} contains the other reading's "
                        f"accepted form {form!r}.\n"
                        f"  A system that echoed the question would be recorded as "
                        f"having returned the wrong version."
                    )


def _norm(text: str) -> str:
    return " ".join((text or "").split()).casefold()
