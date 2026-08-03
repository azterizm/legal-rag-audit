"""4 — Index freshness / cache invalidation (§8.2 #4, Tier 1).

Plant a fact as invariant `V1`, upload it, ask. Replace the document with a version
carrying `V2`, wait, ask the same question again. `V1` coming back after the revision
means the index was never invalidated.

Three outcomes, and the third is the one that makes the check honest:

* `V1` present after the revision ⇒ **stale index**. The finding.
* `V2` present and `V1` absent ⇒ the revision was picked up. A pass.
* **Neither present ⇒ `NOT_CAPTURED`.** The system answered without either value, so the
  question of which one it held was never reached. Scoring that as a pass would be a
  clean result nobody earned (F40).

The wait between the revision and the second question is recorded in the run manifest
because *"not yet indexed"* and *"never invalidated"* are different findings with
different severity, and only the elapsed time separates them. A run whose wait was
fifteen seconds has not established the second one, and the report must let a reader see
that rather than asking them to assume a sensible number was used.
"""

from typing import Any, Optional

from ._common import FAIL, NOT_CAPTURED, PASS, appeared, result


class IndexFreshnessEvaluator:
    """Which version of a revised fact came back. No model involved."""

    def evaluate(
        self,
        answer: str,
        superseded: list[str],
        current: list[str],
        wait_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        stale = appeared(answer, superseded)
        fresh = appeared(answer, current)

        if stale:
            status, reason = FAIL, None
        elif not fresh:
            status = NOT_CAPTURED
            reason = (
                "the answer carried neither the superseded value nor the current one, "
                "so which version the index held was never reached. Not a pass"
            )
        else:
            status, reason = PASS, None

        return result(
            status,
            appeared=stale,
            absent=[] if fresh else list(current or []),
            reason=reason,
            superseded_present=stale,
            current_present=fresh,
            # On the page beside the finding. A short wait cannot distinguish a cache
            # that never invalidates from one that had not finished indexing.
            wait_seconds=wait_seconds,
        )
