"""15 — Latency (§8.2 #15, Tier 1 measurement plus labelled inference).

Two things live here and the report must never merge them.

**The measurement.** Time to first byte and total response time, per probe, per pass,
reported as a distribution with median and p95. Numbers we observed. They cannot fail:
there is no threshold, because any threshold would be ours rather than a standard, and a
slow answer is not by itself a defect in anybody's retrieval.

**The inference.** A large gap between TTFB and total on a query designed to surface
contradictory documents is consistent with catch-and-regenerate — the system producing an
answer, noticing the conflict, and silently re-running generation. That reading is
*inference about an architecture*, register **By design**, and §8.2 puts it in the
mechanism section (§10.4), never in the Tier 1 findings table.

The v1 evaluator collapsed the two: it failed a record whose contradictory query took
three times the baseline, or exceeded a thirty-second ceiling. So a report could carry a
Tier 1 finding of `latency: FAIL` that was really a claim about somebody's architecture
derived from two numbers and three constants we chose. A vendor answers that by pointing
at their egress, and they are right to. Everything below is either a measurement or a
sentence that says out loud that it is a reading of one.
"""

from typing import Any, Optional

from ._common import PASS, result

#: The gap ratio above which the reading is offered. Not a pass condition — nothing here
#: is — and stated on the page beside the reading so a reader can disagree with the number
#: without having to disagree with the measurement.
SUGGESTIVE_GAP_RATIO = 3.0

REGISTER = "By design"

INFERENCE_LIMIT = (
    "This is a reading of two timings, not a measurement of an architecture. A gap "
    "between first byte and completion is consistent with a second generation pass; it "
    "is also consistent with a long retrieval, a cold cache, a rate limit, or a slow "
    "link. It appears in the mechanism section for that reason and is not a finding"
)


def _percentile(values: list[float], fraction: float) -> Optional[float]:
    """Nearest-rank percentile. Deterministic, and no dependency to disclose."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(fraction * len(ordered) + 0.5) - 1))
    return ordered[index]


def _summary(values: list[Optional[float]]) -> dict[str, Any]:
    present = [v for v in values if v is not None]
    return {
        "observations": len(present),
        "not_captured": len(values) - len(present),
        "median_ms": _percentile(present, 0.5),
        "p95_ms": _percentile(present, 0.95),
        "min_ms": min(present) if present else None,
        "max_ms": max(present) if present else None,
    }


class LatencyPenaltyEvaluator:
    """Timings as distributions, and the catch-and-regenerate reading kept separate."""

    def measure(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Distributions over every timed record. Never a single figure (§8.2 #15)."""
        return {
            "ttfb": _summary([r.get("ttfb_ms") for r in records]),
            "total": _summary([r.get("total_ms") for r in records]),
            "records": len(records),
        }

    def compare(
        self,
        baseline_total: Optional[float],
        contradictory_total: Optional[float],
        baseline_ttfb: Optional[float] = None,
        contradictory_ttfb: Optional[float] = None,
    ) -> dict[str, Any]:
        """The paired reading, labelled as inference and carrying its own limit line."""
        total_ratio = _ratio(baseline_total, contradictory_total)
        ttfb_ratio = _ratio(baseline_ttfb, contradictory_ttfb)

        suggestive = any(
            r is not None and r >= SUGGESTIVE_GAP_RATIO for r in (total_ratio, ttfb_ratio)
        )

        return {
            "register": REGISTER,
            "baseline_total_ms": baseline_total,
            "contradictory_total_ms": contradictory_total,
            "baseline_ttfb_ms": baseline_ttfb,
            "contradictory_ttfb_ms": contradictory_ttfb,
            "total_ratio": total_ratio,
            "ttfb_ratio": ttfb_ratio,
            "gap_ratio_considered_suggestive": SUGGESTIVE_GAP_RATIO,
            "reading": (
                "the contradictory query took materially longer than the baseline, "
                "which is consistent with a second generation pass"
                if suggestive
                else "no material difference between the two queries"
            ),
            "limit": INFERENCE_LIMIT,
            "ttfb_captured": baseline_ttfb is not None and contradictory_ttfb is not None,
        }

    def evaluate(
        self,
        records: list[dict[str, Any]],
        inference: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """The check's result: a measurement, so its status is always PASS."""
        return result(
            PASS,
            measurement=True,
            distributions=self.measure(records),
            inference=inference,
        )


def _ratio(baseline: Optional[float], other: Optional[float]) -> Optional[float]:
    if not baseline or other is None:
        return None
    return round(other / baseline, 2)
