"""13 — Retrieval disambiguation (§8.2 #13, Tier 1).

Two statutes both contain an "Article 5", each carrying a distinct planted invariant. The
question names the statute. Which invariant came back is the whole result:

* the right one only ⇒ pass;
* the wrong one only ⇒ **vector collision** — the retriever matched on the shared surface
  form and fetched the other document;
* both ⇒ **merged concepts** — the two articles were blended into one answer, which is
  worse than fetching the wrong one because the output looks authoritative on both;
* neither ⇒ `NOT_CAPTURED`.

**Latency is recorded and is never the pass condition.** The v1 evaluator failed a record
whose response time exceeded a thirty-second ceiling, on the theory that a slow answer
indicates a ReAct loop thrashing between the two articles. That is inference about an
architecture, and §8.2 #15 is explicit that such inference belongs in the mechanism
section under the register *By design* — never in a Tier 1 findings table. A slow network
is not a retrieval defect, and a check that could fail on one is a check whose findings a
vendor can dismiss by pointing at their egress.
"""

from typing import Any, Optional

from ._common import FAIL, NOT_CAPTURED, PASS, appeared, result


class RetrievalDisambiguationEvaluator:
    """Which colliding article's invariant appeared. No model involved."""

    def evaluate(
        self,
        answer: str,
        expected: list[str],
        forbidden: list[str] = (),
        latency_seconds: Optional[float] = None,
    ) -> dict[str, Any]:
        correct = appeared(answer, expected)
        wrong = appeared(answer, forbidden)

        if correct and wrong:
            status, outcome = FAIL, "merged_concepts"
        elif wrong:
            status, outcome = FAIL, "vector_collision"
        elif correct:
            status, outcome = PASS, "disambiguated"
        else:
            status, outcome = NOT_CAPTURED, "neither_invariant_returned"

        return result(
            status,
            appeared=wrong,
            absent=[e for e in (expected or []) if e not in correct] if wrong else [],
            outcome=outcome,
            reason=(
                "the answer carried neither statute's invariant, so which document was "
                "retrieved was never observable. Not a pass"
                if status == NOT_CAPTURED
                else None
            ),
            correct_invariants=correct,
            wrong_invariants=wrong,
            # A measurement carried alongside, for the mechanism section. It cannot
            # change the verdict above.
            latency_seconds=(
                round(latency_seconds, 3) if latency_seconds is not None else None
            ),
        )
