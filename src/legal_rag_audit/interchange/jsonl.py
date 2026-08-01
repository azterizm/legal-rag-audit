"""JSONL reading and writing, with errors that name the line.

These files are written by people who are not us (F35), so a parse failure has to say
which line, what was wrong, and what was expected. A stack trace does not survive
being forwarded to the engineer who produced the file.
"""

import json
from pathlib import Path
from typing import Any, Iterator


class InterchangeError(Exception):
    """A malformed interchange file. A setup problem, not a finding (NF9)."""


def read_records(path: str | Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield `(line_number, object)` for each non-blank line.

    Line numbers are 1-based and count blank lines, so they match what an editor
    shows. Blank lines are skipped: a trailing newline is not an error.
    """
    p = Path(path)
    if not p.exists():
        raise InterchangeError(f"{p}: no such file.")
    if p.is_dir():
        raise InterchangeError(f"{p}: is a directory, expected a JSONL file.")

    seen = 0
    with p.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                raise InterchangeError(
                    f"{p}:{lineno}: not valid JSON ({e.msg} at column {e.colno}).\n"
                    f"  Each line must be one complete JSON object. A pretty-printed\n"
                    f"  object spanning several lines is the usual cause — use `jq -c`."
                ) from None
            if not isinstance(obj, dict):
                raise InterchangeError(
                    f"{p}:{lineno}: expected a JSON object, found {type(obj).__name__}."
                )
            seen += 1
            yield lineno, obj

    if seen == 0:
        raise InterchangeError(
            f"{p}: no records. An empty file is a setup problem, not an empty result."
        )


def write_records(path: str | Path, records: list[dict[str, Any]]) -> None:
    """Write one compact JSON object per line, keys in insertion order.

    `sort_keys` is deliberately off: the models emit fields in declaration order, which
    is the order the schema documents them in, and a human reading the file should see
    `probe_id` before `raw_response`. Byte-stability comes from the model's field order
    being fixed, not from sorting.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")
