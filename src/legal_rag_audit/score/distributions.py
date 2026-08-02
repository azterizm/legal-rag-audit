"""Tier 2 as a distribution, with the configured line marked (F24, §19 item 7).

A Tier 2 check that printed only PASS or FAIL would hide the two things a reader has
to see. First, **how close to the line every record sat** — twelve records at 0.84
against a line of 0.85 is a different system from twelve at 0.11, and both are "FAIL".
Second, that **the line is a setting of ours**. `0.85` and `0.02` are configured
numbers, not standards, and printing a verdict without the distribution behind it
presents a choice we made as a property of somebody's product.

So every Tier 2 check carries its numbers, its buckets, and the line drawn on the
correct side — which is not the same side for all three (`instruments.better`).

No percentages here either (§3.5). Counts per bucket, and the denominator is the count
of records that produced a number.
"""

from statistics import mean, median
from typing import Any, Optional

from ..instruments import BY_CHECK

#: Ten fixed buckets across [0, 1]. Fixed rather than fitted to the observed range:
#: buckets that move with the data make two runs of the same check incomparable, and
#: the whole point of the distribution is that a reader can put two reports side by
#: side. Every instrument here produces a number in [0, 1].
BUCKET_COUNT = 10


def _bucket_index(value: float) -> int:
    if value >= 1.0:
        return BUCKET_COUNT - 1
    if value <= 0.0:
        return 0
    return min(int(value * BUCKET_COUNT), BUCKET_COUNT - 1)


def _label(index: int) -> str:
    low = index / BUCKET_COUNT
    high = (index + 1) / BUCKET_COUNT
    closing = "]" if index == BUCKET_COUNT - 1 else ")"
    return f"[{low:.1f}, {high:.1f}{closing}"


def build(
    check: str, per_probe: list[dict[str, Any]], threshold: float
) -> Optional[dict[str, Any]]:
    """The distribution for one Tier 2 check, or None if it has no instrument.

    `per_probe` is the scorer's own output — one dict per record, carrying `probe_id`,
    `pass_index` and whatever the evaluator returned. The number is pulled by the key
    named in the instrument table rather than guessed, because the three evaluators
    call it three different things and a heuristic would silently pick the wrong field
    the first time one of them gains a second float.
    """
    instrument = BY_CHECK.get(check)
    if instrument is None:
        return None

    observations = []
    missing = 0
    for record in per_probe:
        value = record.get(instrument.score_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            observations.append(
                {
                    "probe_id": record.get("probe_id"),
                    "pass_index": record.get("pass_index"),
                    "score": round(float(value), 4),
                }
            )
        else:
            # A record the evaluator scored without producing the number. Counted, not
            # dropped: a distribution over an unstated subset of the records is a
            # distribution with an invisible denominator.
            missing += 1

    scores = [o["score"] for o in observations]
    out_of_range = sum(1 for s in scores if s < 0.0 or s > 1.0)

    counts = [0] * BUCKET_COUNT
    for value in scores:
        counts[_bucket_index(value)] += 1

    if instrument.better == "higher":
        passing = sum(1 for s in scores if s >= threshold)
        line_reads = f"at or above {threshold} passes"
    else:
        passing = sum(1 for s in scores if s <= threshold)
        line_reads = f"at or below {threshold} passes"

    return {
        "instrument": instrument.model,
        "measures": instrument.unit,
        "line": threshold,
        "line_reads": line_reads,
        "line_is": (
            "a configured setting of this run, not a published standard. It is "
            "recorded in the run manifest with where it came from"
        ),
        "records_with_a_number": len(scores),
        "records_without_a_number": missing,
        "on_the_passing_side": passing,
        "on_the_failing_side": len(scores) - passing,
        "min": round(min(scores), 4) if scores else None,
        "max": round(max(scores), 4) if scores else None,
        "mean": round(mean(scores), 4) if scores else None,
        "median": round(median(scores), 4) if scores else None,
        "out_of_range": out_of_range,
        "buckets": [
            {
                "range": _label(index),
                "count": count,
                # Which buckets the line cuts between. Marked in the data rather than
                # left to the renderer, so a consumer that draws its own chart cannot
                # draw the line in the wrong place.
                "side": _side(index, threshold, instrument.better),
            }
            for index, count in enumerate(counts)
        ],
        "observations": observations,
    }


def _side(index: int, threshold: float, better: str) -> str:
    """Which side of the line a bucket falls on, or that it straddles it."""
    low = index / BUCKET_COUNT
    high = (index + 1) / BUCKET_COUNT
    if low < threshold < high:
        return "straddles the line"
    if better == "higher":
        return "passing" if low >= threshold else "failing"
    return "passing" if high <= threshold else "failing"


def render(distribution: dict[str, Any], width: int = 32) -> list[str]:
    """The distribution as text rows, for the Markdown attestation.

    A bar chart in a Markdown table, because the attestation has to be readable as a
    document rather than only as a file a tool renders.
    """
    counts = [bucket["count"] for bucket in distribution["buckets"]]
    peak = max(counts) if counts else 0
    rows = []
    for bucket in distribution["buckets"]:
        bar = "█" * round(bucket["count"] / peak * width) if peak else ""
        marker = " ←— line" if bucket["side"] == "straddles the line" else ""
        rows.append(
            f"| `{bucket['range']}` | {bucket['count']:>3} | {bar}{marker} |"
        )
    return rows
