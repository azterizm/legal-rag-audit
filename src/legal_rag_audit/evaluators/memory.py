"""14 — Context window / memory management (§8.2 #14, Tier 1).

A distinct invariant per referent, planted across a document set long enough that holding
all of them is the thing being tested. The question uses a pronoun with one defined
antecedent. **Which referent's invariant appeared** is the result.

Four outcomes, and the second is the finding this check exists for:

* the correct referent only ⇒ pass;
* a different referent ⇒ the pronoun resolved to the wrong antecedent. The answer is
  fluent, specific and about the wrong party;
* several ⇒ ambiguous resolution: the system offered more than one referent as the answer
  to a question with a single one;
* none ⇒ `NOT_CAPTURED`.

The v1 evaluator checked one string and returned pass or fail. That cannot tell a system
that resolved incorrectly from one that did not answer, and those are different findings.
"""

from typing import Any

from ._common import FAIL, NOT_CAPTURED, PASS, appeared, result


class MemoryManagementEvaluator:
    """Which referent the pronoun resolved to. No model involved."""

    def evaluate(
        self,
        answer: str,
        expected: list[str],
        other_referents: list[str] = (),
    ) -> dict[str, Any]:
        correct = appeared(answer, expected)
        others = appeared(answer, other_referents)

        if correct and others:
            status, outcome = FAIL, "ambiguous_resolution"
        elif others:
            status, outcome = FAIL, "wrong_referent"
        elif correct:
            status, outcome = PASS, "resolved"
        else:
            status, outcome = NOT_CAPTURED, "no_referent_returned"

        return result(
            status,
            appeared=others,
            absent=[e for e in (expected or []) if e not in correct] if others else [],
            outcome=outcome,
            reason=(
                "the answer named none of the planted referents, so which one the "
                "pronoun resolved to was never observable. Not a pass"
                if status == NOT_CAPTURED
                else None
            ),
            resolved_to=correct + others,
            referents_declared=len(expected or []) + len(other_referents or []),
        )
