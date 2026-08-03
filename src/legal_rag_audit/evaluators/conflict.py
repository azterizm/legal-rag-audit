"""9 — Contradiction surfacing (§8.2 #9, Tier 1).

Two near-identical agreements carry contradictory values, each a distinct planted
invariant. The question asks for the value. Three outcomes:

* **Both present** ⇒ the conflict was surfaced. Pass.
* **Exactly one present** ⇒ the system silently picked a side. Fail — and *which* side
  it picked is recorded, because a system that consistently returns the superseded
  version is a different problem from one that picks at random.
* **Neither present** ⇒ `NOT_CAPTURED`. The answer never reached the value, so nothing
  about conflict handling was observed. Not a pass (F40).

The middle case is the commercially serious one and it is invisible in ordinary use: the
answer reads fluently, cites a real document, and omits the fact that another document in
the same index says something else.
"""

from typing import Any

from ._common import FAIL, NOT_CAPTURED, PASS, appeared, result


class ContradictionSurfacingEvaluator:
    """Both sides of a planted contradiction, or which one won. No model involved."""

    def evaluate(self, answer: str, values: list[str]) -> dict[str, Any]:
        sides = list(values or [])
        surfaced = appeared(answer, sides)

        if len(surfaced) >= 2:
            status, outcome, reason = PASS, "surfaced", None
        elif not surfaced:
            status, outcome = NOT_CAPTURED, "neither_value_returned"
            reason = (
                "the answer carried neither planted value, so nothing was observed "
                "about how the system handles the conflict. Not a pass"
            )
        else:
            status, outcome, reason = FAIL, "silently_picked", None

        return result(
            status,
            # The side that was suppressed is the evidence: the answer looks complete
            # precisely because the other value is missing from it.
            absent=[] if status != FAIL else [s for s in sides if s not in surfaced],
            outcome=outcome,
            reason=reason,
            surfaced=surfaced,
            picked=surfaced[0] if status == FAIL else None,
            sides=len(sides),
        )
