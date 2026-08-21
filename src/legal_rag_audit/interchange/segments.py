"""Running one battery across several accounts, and joining the pieces honestly.

A free trial answers a handful of questions and then returns `402`. The battery is 22
probes and the recommendation is three passes, so no single trial account can carry a
run. The August captures already hit this and solved it by hand — `merge_runs.py` beside
the Writford run joined two accounts' files and wrote a paragraph explaining what it had
done. This is that procedure as a command, because a step that only ever existed as a
one-off script is a step nobody can check.

**`outstanding` decides what is left.** It reads the probe file and every response file
gathered so far, counts the passes that came back *with an answer*, and reports the
shortfall per probe. A record carrying a transport error is not an answer: the probe it
names is still outstanding, which is the whole reason the first Writford account's `402`s
had to be re-asked rather than merged in.

**`merge_segments` joins them.** It drops error records superseded by an answer from a
later segment, keeps every surviving record verbatim, and renumbers `pass_index` so the
merged file satisfies the reader's one-record-per-`(probe_id, pass_index)` rule. Nothing
else is touched — no answer, citation or timestamp is edited, and each record keeps the
`run_id` of the run that produced it, which is what lets a reader take the merge apart
again.

## The thing this must never be quiet about

Passes collected from **different accounts are not the same measurement** as passes
collected from one session. `response_divergence` asks whether a system returns the same
answer to the same question asked three times; across accounts it is also measuring quota
tier, per-account personalisation, model routing, and whatever else the product varies by
user. Those are different claims and only one of them is reproducibility.

So a merged file carries the fact in its own `capture_notes`, in the header the report
reads, rather than in a README beside it. `merge_segments` refuses to write a file that
does not say how many segments it came from. A reader who is handed only the merged file
still learns that it was assembled — which is the property the whole interchange format
exists to preserve.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .jsonl import InterchangeError, read_records

#: Prepended to whatever note the operator supplies. Not optional and not configurable:
#: it is the sentence a reader needs and the one an assembler is most tempted to leave
#: out.
ASSEMBLED = (
    "ASSEMBLED FROM {n} SEGMENTS, not captured in one run. Passes for a probe may come "
    "from different accounts of the same product, so `response_divergence` across them "
    "measures account-to-account variation as well as within-session reproducibility; "
    "those are different claims and the stronger one is not supported. No answer, "
    "citation or timestamp was altered. Records carrying a transport error were dropped "
    "where a later segment answered the same probe. `pass_index` was renumbered per "
    "probe so the file satisfies one-record-per-(probe_id, pass_index); each record "
    "keeps the `run_id` of the run that produced it."
)


def _answered(record: dict[str, Any]) -> bool:
    """Whether this record carries a result rather than a failed measurement."""
    return not record.get("error") and bool((record.get("answer") or "").strip())


def _load(path: str | Path) -> tuple[Optional[dict], list[dict]]:
    header, rows = None, []
    for _, obj in read_records(path):
        if obj.get("record") == "capture_notes":
            header = obj
        elif "probe_id" in obj:
            rows.append(obj)
    return header, rows


@dataclass
class Outstanding:
    """What is still to ask, and what has already been gathered."""

    target_passes: int
    #: `probe_id -> passes still needed`, only probes with a shortfall.
    remaining: dict[str, int] = field(default_factory=dict)
    #: `probe_id -> passes already answered`, every probe in the battery.
    gathered: dict[str, int] = field(default_factory=dict)
    #: Probes named in a response file that the probe file does not contain.
    unknown: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.remaining

    @property
    def next_passes(self) -> int:
        """The `--passes` to give the next segment: the largest single shortfall."""
        return max(self.remaining.values(), default=0)


def outstanding(
    probes_path: str | Path,
    response_paths: list[str | Path],
    target_passes: int,
) -> Outstanding:
    """Count answered passes per probe and report the shortfall against `target_passes`."""
    if target_passes < 1:
        raise InterchangeError(f"target passes must be at least 1, got {target_passes}")

    order: list[str] = []
    for _, obj in read_records(probes_path):
        if "probe_id" in obj:
            order.append(obj["probe_id"])
    if not order:
        raise InterchangeError(f"{probes_path}: no probe records.")

    counts = {pid: 0 for pid in order}
    unknown: list[str] = []
    for path in response_paths:
        _, rows = _load(path)
        for row in rows:
            pid = row.get("probe_id")
            if pid not in counts:
                if pid not in unknown:
                    unknown.append(pid)
                continue
            if _answered(row):
                counts[pid] += 1

    remaining = {
        pid: target_passes - counts[pid]
        for pid in order
        if counts[pid] < target_passes
    }
    return Outstanding(
        target_passes=target_passes,
        remaining=remaining,
        gathered=counts,
        unknown=unknown,
    )


def write_remaining_probes(
    probes_path: str | Path, out_path: str | Path, state: Outstanding
) -> int:
    """Write a probe file holding only the probes that still need passes.

    Order is preserved from the source file, so a battery whose abstention family was
    moved to the front stays that way in every segment — which is the point of having
    moved it. Returns the number of probes written.
    """
    if state.complete:
        raise InterchangeError(
            "Nothing is outstanding: every probe has its full complement of answered "
            "passes.\n  Merge the segments instead."
        )

    kept: list[dict[str, Any]] = []
    for _, obj in read_records(probes_path):
        if obj.get("probe_id") in state.remaining:
            kept.append(obj)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for obj in kept:
            fh.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(kept)


def merge_segments(
    response_paths: list[str | Path],
    out_path: str | Path,
    *,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Join response files into one, dropping superseded failures. Returns a summary.

    Segments are read in the order given, and that order is the precedence: an answer
    always beats an error, and where two segments both answered a probe both records are
    kept as separate passes.
    """
    if len(response_paths) < 2:
        raise InterchangeError(
            "A merge needs at least two response files.\n"
            "  One segment is already a response file; merging it would only copy it."
        )

    header: Optional[dict[str, Any]] = None
    by_probe: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    dropped = 0

    for path in response_paths:
        seg_header, rows = _load(path)
        if header is None and seg_header is not None:
            # The first segment's header declares what the capture could record. Later
            # segments are the same battery against the same product, so a differing
            # header is a setup problem rather than something to silently reconcile.
            header = dict(seg_header)
        for row in rows:
            pid = row["probe_id"]
            if pid not in by_probe:
                by_probe[pid] = []
                order.append(pid)
            by_probe[pid].append(row)

    merged: list[dict[str, Any]] = []
    for pid in order:
        rows = by_probe[pid]
        answers = [r for r in rows if _answered(r)]
        # An error record is a failed measurement. Keep it only when nothing else for
        # this probe succeeded — otherwise it would pad the denominator with a failure
        # a later account already answered.
        keep = answers if answers else rows[:1]
        dropped += len(rows) - len(keep)
        for index, row in enumerate(keep, start=1):
            record = dict(row)
            record["pass_index"] = index
            merged.append(record)

    if header is None:
        raise InterchangeError(
            "No segment carried a `capture_notes` header.\n"
            "  The merged file must declare what the capture could record, and an "
            "assembled file must say that it was assembled."
        )

    preamble = ASSEMBLED.format(n=len(response_paths))
    header["notes"] = f"{preamble} {note}".strip() if note else preamble

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for record in [header, *merged]:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    return {
        "segments": len(response_paths),
        "probes": len(order),
        "records": len(merged),
        "answered": sum(1 for r in merged if _answered(r)),
        "dropped_superseded": dropped,
        "passes_per_probe": {pid: len(by_probe[pid]) for pid in order},
    }
