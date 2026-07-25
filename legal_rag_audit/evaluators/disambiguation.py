import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class RetrievalDisambiguationEvaluator:
    """
    Tests whether the RAG system can distinguish between overlapping entities
    that share the same surface-level identifier (e.g., "Article 5") but come
    from entirely different statutes.

    The bundled corpus includes:
      - statute_alpha.txt → Article 5: hazardous waste fines ($25,000/day)
      - statute_beta.txt  → Article 5: mandatory binding arbitration (14 days)

    A well-built system should:
      1. Not merge the two articles into a single blended answer.
      2. Clearly attribute each Article 5 to its origin statute.
      3. Not thrash in an infinite ReAct loop trying to reconcile them.

    Detection strategy (deterministic, no LLM):
      - Check that the answer references content from the *correct* statute
        for the query (via expected canary phrases).
      - Check that the answer does NOT leak content from the *wrong* statute.
      - Optionally flag if both are conflated into a single undifferentiated
        answer (no source attribution).
    """

    def __init__(self):
        pass

    def evaluate(
        self,
        answer: str,
        expected_canaries: List[str],
        forbidden_canaries: List[str],
        latency_seconds: float = 0.0,
        latency_ceiling: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Evaluate disambiguation quality.

        Args:
            answer: The system's response text.
            expected_canaries: Key phrases that MUST appear (from the correct
                               statute for this query). Case-insensitive.
            forbidden_canaries: Key phrases that MUST NOT appear (from the
                                wrong statute). Case-insensitive.
            latency_seconds: Observed response time. If the system spent an
                             excessive amount of time, it may be thrashing.
            latency_ceiling: Maximum acceptable latency before flagging
                             potential ReAct loop thrashing.

        Returns:
            Result dict with status, found/leaked canaries, and thrash flag.
        """
        answer_lower = answer.lower()
        failures: List[str] = []

        # --- Check expected canaries from the correct statute ---
        found_expected = [c for c in expected_canaries if c.lower() in answer_lower]
        missing_expected = [c for c in expected_canaries if c.lower() not in answer_lower]

        if missing_expected:
            failures.append(
                f"Missing expected content from correct statute: "
                f"{missing_expected}"
            )

        # --- Check forbidden canaries from the wrong statute ---
        leaked_forbidden = [c for c in forbidden_canaries if c.lower() in answer_lower]

        if leaked_forbidden:
            failures.append(
                f"Answer contains content from wrong statute "
                f"(context merging detected): {leaked_forbidden}"
            )

        # --- Check for ReAct loop thrashing via latency ---
        thrash_detected = False
        if latency_seconds > latency_ceiling:
            thrash_detected = True
            failures.append(
                f"Response latency ({latency_seconds:.1f}s) exceeds ceiling "
                f"({latency_ceiling}s) — possible ReAct loop thrashing"
            )

        status = "FAIL" if failures else "PASS"

        return {
            "status": status,
            "expected_found": len(found_expected),
            "expected_total": len(expected_canaries),
            "forbidden_leaked": len(leaked_forbidden),
            "thrash_detected": thrash_detected,
            "latency_seconds": round(latency_seconds, 2),
            "details": {
                "found_expected": found_expected,
                "missing_expected": missing_expected,
                "leaked_forbidden": leaked_forbidden,
                "failures": failures,
            } if failures else {
                "found_expected": found_expected,
            }
        }
