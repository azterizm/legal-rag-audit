"""11 — Cross-clause synthesis (§8.2 #11, Tier 1).

An obligation in clause 4, an exclusion in clause 19 that qualifies it, each carrying its
own invariant. The question asks whether the obligation applies in the excluded case.

A required-facts checklist, and the required fact that matters is the **exclusion**.
Omitting it is the finding, and §8.2 calls it the single most commercially serious
retrieval failure in contract work: the answer is fluent, cites a real clause, states a
real obligation, and is wrong in the only way that costs money — it does not mention the
carve-out that makes the obligation not apply.

Nothing about this needs a model. The exclusion is a string we planted at a declared
location; it either came back or it did not.
"""

from typing import Any

from ._common import FAIL, PASS, absent, appeared, result


class CrossClauseSynthesisEvaluator:
    """Every required fact, including the planted exclusion. No model involved."""

    def evaluate(self, answer: str, required_facts: list[str]) -> dict[str, Any]:
        required = list(required_facts or [])
        missing = absent(answer, required)

        return result(
            FAIL if missing else PASS,
            absent=missing,
            found=appeared(answer, required),
            facts_required=len(required),
            outcome="incomplete_synthesis" if missing else "complete",
        )
