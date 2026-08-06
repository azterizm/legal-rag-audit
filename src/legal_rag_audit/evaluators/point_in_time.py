"""Point-in-time correctness (§9.2, F27, Tier 1).

Per [Source Map §2] the strongest untaken measurement in this market, and the reason is
that it is unarguably a **legal**-correctness question rather than an engineering-taste
one. A system that returns the law as it stands in answer to a question about what it was
on a date has not returned a worse answer; it has returned an answer to a different
question, and in practice that is advice about the wrong legal test.

Ground truth is external and public: the version of a provision in force on a date,
identified by a short phrase quoted from `legislation.gov.uk` (`external.anchors`). No
model, no similarity, no threshold — the phrase either came back or it did not, exactly
as with a planted invariant.

**Both versions present is a pass, and that is the important decision here.** An answer to
*"as at 1 January 2011"* that says *"the period was then not less than one year; it is now
not less than two years"* is better than the one we asked for, not worse. Scoring the
presence of the other version as a failure would fail the most useful behaviour a system
can exhibit — and §14.2 makes a false positive a release blocker. So the finding is only
ever *the correct version is **absent** and the superseded one is there*.

**`version_mismatch` is the counter, not a separate check** (§10.5). An answer that names
the provision correctly and then gives the wrong version's text is the serious form: it
reads as authoritative, cites something a reader can look up, and is wrong about the only
thing that mattered. Counted apart from an answer that gets both wrong, because a reader
triaging findings needs to know which of the two they have.

**Neither version is three outcomes, not one** (defect 20). The first live run of this
battery put ten of twelve probes in the neither branch, and they were not the same event.
One target answer said *"I could not produce a grounded answer"*; another gave **£751 per
week** cited to the section asked about, when that section read £508 on the date asked and
£751 was the current figure from a different section of the same Act. Both printed
`no_version_returned`, which is F40 exactly — an absent measurement and a failed one
reading the same on the page. A system that knows it does not know and a system that
transplants a figure from elsewhere deserve different pages.

The split is made the way `AbstentionEvaluator` makes it, and deliberately the same way:
**by the presence of a claim, never by the absence of refusal language.** Enumerating
refusal phrasings is the trap §8.2 #8 names by hand. The shapes come from the anchor's own
readings — an anchor whose readings are `£450` and `£508` is asking for a figure, so a
figure in the answer that is neither of them is an answer in neither version, and no figure
at all is a declination.

None of the three is a finding. Which version was retrieved was never observable in any of
them, and inventing a failure out of our own inability to observe is the thing §14.2 makes
a release blocker. What changes is what the reader is told they are looking at.

Where the readings are prose that matches no shape — `not less than one year` is a duration
written in words, and the shared shape vocabulary requires a digit — the split cannot be
made and the outcome stays `no_version_returned` with that stated. Widening the shared
shapes to reach it was rejected: they are also what `abstention` scores findings on, and a
looser figure rule there produces false positives on a check that fails people.
"""

from typing import Any, Optional

from ._common import (
    FAIL,
    NOT_CAPTURED,
    PASS,
    SHAPES,
    appeared,
    claims_of_shape,
    present,
    result,
)


def shapes_of(readings) -> list[str]:
    """Which claim shapes the anchor's own readings are written in.

    Read off the ground truth rather than declared beside it, so an anchor added to
    `external.anchors` cannot arrive with the two out of step. The cost is that a reading
    the shared vocabulary cannot see — a duration spelled out in words — yields nothing,
    and the caller says so rather than guessing.
    """
    return [
        name
        for name, pattern in SHAPES.items()
        if any(pattern.search(r) for r in readings if r)
    ]


class PointInTimeEvaluator:
    """Which version of a provision came back for the date asked. No model involved."""

    def evaluate(
        self,
        answer: str,
        in_force: list[str],
        superseded: list[str] = (),
        provision: Optional[str] = None,
        as_at: Optional[str] = None,
        question: str = "",
    ) -> dict[str, Any]:
        correct = appeared(answer, in_force)
        wrong = appeared(answer, superseded)
        # Whether the answer identified the provision it was talking about. Only
        # meaningful alongside a wrong version, where it separates a confident error
        # from a vague one.
        cited = bool(provision) and present(answer, provision)
        offered: list[str] = []

        if correct:
            status = PASS
            outcome = "version_correct_with_context" if wrong else "version_correct"
            reason = None
        elif wrong:
            status = FAIL
            outcome = "version_mismatch"
            reason = None
        else:
            status = NOT_CAPTURED
            outcome, reason, offered = self._neither(
                answer, list(in_force) + list(superseded), question
            )

        return result(
            status,
            appeared=wrong if status == FAIL else [],
            absent=list(in_force) if status == FAIL else [],
            outcome=outcome,
            reason=reason,
            # On the page beside the finding. "Wrong version" means nothing without the
            # date the question asked about.
            as_at=as_at or "the law as it stands",
            provision=provision,
            # §9.2's sharper form: the right provision, the wrong text.
            provision_cited_correctly=cited,
            version_mismatch_with_correct_citation=bool(status == FAIL and cited),
            in_force_present=correct,
            superseded_present=wrong,
            # What the answer asserted instead, where it asserted anything. Deliberately
            # not `appeared`: that key is the evidence bundle's contract for findings,
            # and none of these is one. It is here so a reader triaging ten unscoreable
            # records can see which of them said £751 and which said nothing.
            claims_offered=offered,
        )

    def _neither(
        self, answer: str, readings: list[str], question: str
    ) -> tuple[str, str, list[str]]:
        """Which of the three neither-version outcomes this answer is (defect 20)."""
        shapes = shapes_of(readings)
        if not shapes:
            return (
                "no_version_returned",
                "the answer carried neither the version in force on the date asked nor "
                "the superseded one, so which version was retrieved was never "
                "observable. Not a pass. Whether the answer declined or asserted "
                "something else is not recorded here: the readings for this anchor are "
                "written in a form the claim-shape rule cannot see, so the distinction "
                "would have been a guess",
                [],
            )

        # The question's own words are excluded before matching, exactly as in
        # `abstention`: a system that restates the figure it was asked about and then
        # declines has echoed the prompt, not answered.
        offered = claims_of_shape(answer, shapes, exclude=question)
        if offered:
            return (
                "answered_in_neither_version",
                "the answer asserted a value of the kind the question asked for and it "
                "was neither the version in force on the date asked nor the superseded "
                "one. Not scoreable against the pair, and not a pass: what the value is "
                "and where it came from is a triage question this check does not answer",
                offered,
            )
        return (
            "declined_to_state_a_version",
            "the answer asserted no value of the kind the question asked for, so which "
            "version was retrieved was never observable. Not a pass and not a failure — "
            "a system that declines to state a figure it does not hold has done the safe "
            "thing, and this check cannot see whether it holds one",
            [],
        )
