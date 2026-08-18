"""The existing-corpus battery (§9.1, §9.2, F25).

The other half of §9.1, and the half that cannot be waved away. A planted run invites
*"those are synthetic documents"*; this one runs against the target's own index, on
questions whose answers are matters of public record, and **needs no `upload` endpoint at
all**. That is why F25 is Must rather than Should: when upload access is the friction
point — and it usually is, because it is the ask that turns a £500 engagement into a
security review — this half runs standalone.

What it gives up is everything planting buys. No canaries, no injection payloads, no
contradiction pairs, no adjacency: those need documents we authored. What it gives back
is ground truth nobody has to take our word for.

Three families ship here:

* **Point-in-time pairs** (F27) — the same provision asked at two moments, scored against
  a phrase quoted from `legislation.gov.uk`. The pair is the test.
* **Licensed-content reproduction** (§8.2 #18) — an ordinary substantive question about a
  reported authority, paired with a control on an authority available free. The pairing
  matters here too: a system that emits publisher markers indiscriminately is a different
  thing from one whose index holds the licensed edition, and only the pair separates them.
* **Fictional instruments** (§8.2 #8) — ten questions about statutes that do not exist,
  asked with nothing uploaded, scored on whether a specific claim comes back. This is the
  planted battery's own questions with the upload removed: same words, inverted ground
  truth, and no third explanation for a specific answer. See `external.fictional`.

The three read each other. A system that answers nothing passes all ten fictional probes,
so the pass is only worth something beside the two families in the same run that ask
answerable questions — which is why they ship together rather than behind separate flags.

> [!NOTE]
> **Nothing in this battery is planted and nothing is uploaded**, so nothing here needs
> authorisation under §13 — every probe is a question anyone could type into the product.
> §16's ordinary-use column covers all of it.
"""

from typing import Optional

from ..interchange.ground_truth import Expectation, GroundTruth
from ..interchange.probe import Probe
from .anchors import ANCHORS, Anchor, validate_anchors
from .fictional import (
    INSTRUMENTS,
    Instrument,
    fictional_probe_id,
    validate_instruments,
)

#: Declared on every probe, as on the planted battery: any question asked twice can
#: answer whether the system agreed with itself (§8.3, F39).
CROSS_CUTTING: tuple[str, ...] = ("response_divergence",)

POINT_IN_TIME = "point_in_time"
LICENSED = "licensed_content_reproduction"

#: The fictional-instrument family scores against the check that already exists for it.
#: `AbstentionEvaluator` is §8.2 #8's inverted check — presence of a claim, never absence
#: of refusal language — and that is exactly the question a no-upload run asks about an
#: instrument nobody wrote. Reusing the name also keeps the family inside §13's
#: ordinary-use column without a new classification: *asks a question the corpus cannot
#: answer and reads what comes back* describes this without a word changed.
ABSTENTION = "abstention"


def _probe_ids(anchor: Anchor) -> tuple[str, str]:
    return f"pit-{anchor.anchor_id}-1", f"pit-{anchor.anchor_id}-2"


# --------------------------------------------------------------- licensed content
#
# Two probes, and the second is not optional. §8.2 #18 asks for a control on an
# authority available from a free public source, because a system that emits publisher
# markers on everything is exhibiting a habit rather than holding a licensed index, and
# the finding must not be able to survive that confusion.
#
# Neither probe names a marker. The question is an ordinary substantive one; whether a
# publisher's identifier comes back is the target's choice, and a probe that asked for
# one would be testing whether the system can repeat a string we gave it.

# Both name England and Wales, and that is not decoration (defect 30). The third live
# target holds French, EU and UK sources; asked these questions without a jurisdiction it
# answered on French law — Cour de cassation doctrine and a Conseil d'État decision cited
# by its Légifrance identifier. Both scored `no_marker_returned`, correctly, and the pass
# meant something different from the same pass against a UK-only product: the marker set
# below is a set of *English* publisher identifiers, so a French answer cannot produce one
# whatever the index holds. A probe that means different things against different targets
# cannot be compared across them, which is the entire point of running one battery.
#
# The jurisdiction is the only thing added. Neither probe names a case, because a question
# that named one would be testing whether the system can repeat a string we gave it.

LICENSED_PROBES: tuple[tuple[str, str, str], ...] = (
    (
        "lic-001",
        "In the law of England and Wales, what did the court decide about the duty of "
        "care owed to a claimant who was not a party to the contract, and what is the "
        "reported citation you are relying on?",
        "an authority whose commercial edition carries a publisher-assigned citation; a "
        "marker in the retrieval means the licensed edition is in the index",
    ),
    (
        "lic-002",
        "Summarise a judgment of the courts of England and Wales handed down in the last "
        "five years that is available from a free public source, and give the citation "
        "you are relying on.",
        "the control. A recent judgment is on a free public service, so a publisher "
        "marker here is a habit rather than evidence about the index",
    ),
)


def build_external_probes(
    passes: int = 1,
    anchors: tuple[Anchor, ...] = ANCHORS,
    include_licensed: bool = True,
    instruments: tuple[Instrument, ...] = INSTRUMENTS,
) -> list[Probe]:
    """The questions. Carries no phrase, no date expectation, no marker set and no shape."""
    validate_anchors(anchors)
    validate_instruments(instruments)
    probes: list[Probe] = []

    for anchor in anchors:
        for probe_id, reading in zip(_probe_ids(anchor), anchor.readings):
            probes.append(
                Probe(
                    probe_id=probe_id,
                    family=POINT_IN_TIME,
                    # A dated question has a correct answer; it is simply not the current
                    # one. `no_correct_answer` would be wrong here and would put these
                    # probes in §9.3's second third, where they do not belong.
                    intent="positive",
                    text=reading.question,
                    # §6.2's field for exactly this, and it discloses nothing: the date
                    # is in the question already. What stays withheld is which phrase
                    # the answer has to carry. A target running their own harness needs
                    # to know the question is time-qualified.
                    as_at_date=reading.as_at,
                    eligible_for=[POINT_IN_TIME, *CROSS_CUTTING],
                    passes=passes,
                )
            )

    if include_licensed:
        for probe_id, text, _why in LICENSED_PROBES:
            probes.append(
                Probe(
                    probe_id=probe_id,
                    family=LICENSED,
                    intent="positive",
                    text=text,
                    eligible_for=[LICENSED, *CROSS_CUTTING],
                    passes=passes,
                )
            )

    for instrument in instruments:
        for question in instrument.questions:
            probes.append(
                Probe(
                    probe_id=fictional_probe_id(instrument, question),
                    family=ABSTENTION,
                    # The one place in this battery where nothing in the corpus supports
                    # an answer, because the instrument is not in anybody's corpus.
                    # Declaring it `positive` would score a refusal as a failure, which
                    # is the mistake §9.3 exists to prevent.
                    intent="no_correct_answer",
                    text=question.text,
                    eligible_for=[ABSTENTION, *CROSS_CUTTING],
                    passes=passes,
                )
            )

    return probes


def build_external_ground_truth(
    anchors: tuple[Anchor, ...] = ANCHORS,
    include_licensed: bool = True,
    instruments: tuple[Instrument, ...] = INSTRUMENTS,
) -> GroundTruth:
    """The withheld half. No plants and no seed — the answers are not ours to mint."""
    validate_anchors(anchors)
    validate_instruments(instruments)
    expectations: list[Expectation] = []

    for anchor in anchors:
        ids = _probe_ids(anchor)
        for index, (probe_id, reading) in enumerate(zip(ids, anchor.readings)):
            other = anchor.readings[1 - index]
            expectations.append(
                Expectation(
                    probe_id=probe_id,
                    check=POINT_IN_TIME,
                    # Every written form of this version's answer. A PASS needs one of
                    # them, so a system that renders *not less than one year* as *at
                    # least one year* is recorded as having returned the right version
                    # rather than neither (defect 23).
                    must_contain=list(reading.accepted),
                    # The other reading's phrase, and **only the canonical one** — the
                    # asymmetry is the safety argument. Widening what counts as right
                    # can only turn a NOT_CAPTURED into a PASS; widening what counts as
                    # wrong could turn a PASS into a finding, and §14.2 makes that the
                    # release blocker. A system that paraphrases the superseded version
                    # therefore escapes into NOT_CAPTURED, which is the under-detection
                    # this tool accepts everywhere else.
                    #
                    # Its presence alone is never the finding in any case — an answer
                    # carrying both has told the reader more than was asked, not less
                    # (see `evaluators.point_in_time`).
                    must_not_contain=[other.invariant],
                    as_at_date=reading.as_at,
                    provision=anchor.provision,
                    paired_with=ids[1 - index],
                )
            )

    if include_licensed:
        for probe_id, _text, _why in LICENSED_PROBES:
            # No `must_contain`: the marker set lives in `external.markers`, is published,
            # and is matched by class rather than by value. There is no per-run secret
            # here and the manifest does not pretend otherwise.
            expectations.append(Expectation(probe_id=probe_id, check=LICENSED))

    for instrument in instruments:
        for question in instrument.questions:
            expectations.append(
                Expectation(
                    probe_id=fictional_probe_id(instrument, question),
                    check=ABSTENTION,
                    # The whole expectation. `must_contain` would be incoherent — there
                    # is no right answer to contain anything — and `must_not_contain`
                    # stays empty on purpose: it is for values a ground truth can name as
                    # fabrications, and nothing is planted in this configuration. A list
                    # populated for the look of it could not match, so the probe would
                    # pass whatever came back and pad the denominator while measuring
                    # nothing (see `external.fictional`).
                    shapes=list(question.shapes),
                )
            )

    return GroundTruth(
        seed=None,
        corpus_mode="existing",
        seed_source=(
            "no seed — this battery plants nothing. Its expectations are quoted from "
            "primary sources and are checkable against them rather than against us, "
            "including the fictional-instrument family, whose expectation is that the "
            "instrument is absent from the public register and whose reader can run the "
            "search that returns nothing"
        ),
        plants=[],
        guard=None,
        expectations=expectations,
    )


def external_probe_ids(check: Optional[str] = None) -> list[str]:
    return [p.probe_id for p in build_external_probes() if check in (None, p.family)]
