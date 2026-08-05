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
"""

from typing import Any, Optional

from ._common import FAIL, NOT_CAPTURED, PASS, appeared, present, result


class PointInTimeEvaluator:
    """Which version of a provision came back for the date asked. No model involved."""

    def evaluate(
        self,
        answer: str,
        in_force: list[str],
        superseded: list[str] = (),
        provision: Optional[str] = None,
        as_at: Optional[str] = None,
    ) -> dict[str, Any]:
        correct = appeared(answer, in_force)
        wrong = appeared(answer, superseded)
        # Whether the answer identified the provision it was talking about. Only
        # meaningful alongside a wrong version, where it separates a confident error
        # from a vague one.
        cited = bool(provision) and present(answer, provision)

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
            outcome = "no_version_returned"
            reason = (
                "the answer carried neither the version in force on the date asked nor "
                "the superseded one, so which version was retrieved was never "
                "observable. Not a pass"
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
        )
