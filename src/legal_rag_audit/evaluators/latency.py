import time
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class LatencyPenaltyEvaluator:
    """
    Measures Time-To-First-Byte (TTFB) and total response latency on queries
    designed to trigger contradictory retrieval. A spike in latency (>15s)
    flags a "catch-and-regenerate" architectural flaw — The Hallucination Tax.

    The evaluator is purely timing-based and deterministic: it compares the
    measured latency of a contradictory query against a baseline (non-
    contradictory) query. If the contradictory query is disproportionately
    slower, it indicates the system detected the conflict and silently re-ran
    generation, which is the exact post-hoc regeneration loop the plan
    describes.
    """

    def __init__(self, max_ttfb_seconds: float = 15.0, max_total_seconds: float = 30.0,
                 spike_ratio: float = 3.0):
        """
        Args:
            max_ttfb_seconds: Absolute TTFB ceiling. Any response slower than
                              this is flagged regardless of baseline.
            max_total_seconds: Absolute total latency ceiling.
            spike_ratio: If contradictory_latency / baseline_latency exceeds
                         this ratio, the test fails even if absolute times are
                         below the ceiling. A ratio of 3.0 means the
                         contradictory query took 3× longer than baseline.
        """
        self.max_ttfb_seconds = max_ttfb_seconds
        self.max_total_seconds = max_total_seconds
        self.spike_ratio = spike_ratio

    def evaluate(
        self,
        baseline_ttfb: float,
        baseline_total: float,
        contradictory_ttfb: float,
        contradictory_total: float,
    ) -> Dict[str, Any]:
        """
        Evaluate latency measurements collected by the runner.

        Args:
            baseline_ttfb: TTFB in seconds for the non-contradictory query.
            baseline_total: Total response time in seconds for baseline.
            contradictory_ttfb: TTFB in seconds for the contradictory query.
            contradictory_total: Total response time for contradictory query.

        Returns:
            A result dict with status, measurements, and failure reasons.
        """
        failures: List[str] = []

        # --- Absolute ceiling checks ---
        if contradictory_ttfb > self.max_ttfb_seconds:
            failures.append(
                f"Contradictory TTFB ({contradictory_ttfb:.2f}s) exceeds "
                f"ceiling ({self.max_ttfb_seconds}s)"
            )

        if contradictory_total > self.max_total_seconds:
            failures.append(
                f"Contradictory total latency ({contradictory_total:.2f}s) "
                f"exceeds ceiling ({self.max_total_seconds}s)"
            )

        # --- Spike ratio checks (only meaningful if baseline > 0) ---
        if baseline_ttfb > 0:
            ttfb_ratio = contradictory_ttfb / baseline_ttfb
            if ttfb_ratio > self.spike_ratio:
                failures.append(
                    f"TTFB spike ratio {ttfb_ratio:.1f}× exceeds "
                    f"threshold {self.spike_ratio}× "
                    f"(baseline {baseline_ttfb:.2f}s → "
                    f"contradictory {contradictory_ttfb:.2f}s)"
                )
        else:
            ttfb_ratio = 0.0

        if baseline_total > 0:
            total_ratio = contradictory_total / baseline_total
            if total_ratio > self.spike_ratio:
                failures.append(
                    f"Total latency spike ratio {total_ratio:.1f}× exceeds "
                    f"threshold {self.spike_ratio}× "
                    f"(baseline {baseline_total:.2f}s → "
                    f"contradictory {contradictory_total:.2f}s)"
                )
        else:
            total_ratio = 0.0

        status = "FAIL" if failures else "PASS"

        return {
            "status": status,
            "baseline_ttfb": round(baseline_ttfb, 3),
            "baseline_total": round(baseline_total, 3),
            "contradictory_ttfb": round(contradictory_ttfb, 3),
            "contradictory_total": round(contradictory_total, 3),
            "ttfb_spike_ratio": round(ttfb_ratio, 2),
            "total_spike_ratio": round(total_ratio, 2),
            "max_ttfb_seconds": self.max_ttfb_seconds,
            "max_total_seconds": self.max_total_seconds,
            "spike_ratio_threshold": self.spike_ratio,
            "details": {
                "failures": failures
            } if failures else {}
        }
