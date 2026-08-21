"""Externalise `raw_response` into one file per observation, and put it back.

A response file carries two things with completely different working lives. The record —
`probe_id`, `query`, `answer`, `error`, timings — is what a person reads, what `score`
consumes, and what goes in an evidence bundle. `raw_response` is the target's own wire
capture, kept verbatim so a finding can be re-derived by someone who does not trust us.

Storing them in the same file makes the second one ruin the first. A streamed target
emits every frame it sent: on the 7 August Ordalie run one probe carried 914 SSE frames,
2.5 MB, of which the answer was 2,408 bytes. The file that holds fifteen records is
72 MB, and a fifteen-line file that no ordinary editor will open is not a file anyone
audits — it is a file people take on trust, which is the one thing this project refuses
to ask for.

**The split.** `raw_response` moves to `raw/<probe_id>.pass<N>.json`, one file per
`(probe_id, pass_index)`, and the field is nulled in the record. Each sidecar is
independent and named for the observation it belongs to, so reading the frames behind one
probe means opening one small file rather than seeking into a large one. The lean
`responses.jsonl` stays a JSONL file of the same schema, readable by the same reader, and
small enough to open anywhere.

**Why this is safe to do to evidence.** Because it is reversible and the reversal is
checked rather than asserted. `split_response_file` rehydrates its own output in memory
and compares the SHA-256 against the source before writing anything. A split that would
not round-trip byte-for-byte does not happen; it raises. The digest of the source file is
recorded in `raw/index.json` beside the digest of every sidecar, so the chain from the
original capture to the split pair is checkable by a third party with `shasum`.

**What scoring loses: nothing, on every run this project has done.** `score` reads
`raw_response` in exactly one place — `_score_entity_masking`, and only when the value is
a `dict`. Every streamed capture is a `list` of frames, so scoring already ignores it. The
one check that could read it is `entity_masking`, which needs a planted corpus with swaps
and mask tokens and therefore never fires in `corpus.mode: existing`. `split` still warns
when it externalises a dict, because "never fires today" is a property of the runs done so
far and not of the format.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .jsonl import InterchangeError, read_records

#: Default name of the sidecar directory, relative to the lean file.
RAW_DIRNAME = "raw"

#: Anything outside this is replaced in a sidecar filename. Probe identifiers are ours
#: and are already tame, but a response file may be written by someone else (F35) and a
#: `probe_id` of `../../etc/passwd` must land in the raw directory like anything else.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sidecar_name(probe_id: str, pass_index: int) -> str:
    """`<probe_id>.pass<N>.json`, with the identifier made filesystem-safe.

    Collisions are impossible rather than unlikely: the reader already refuses a file
    with two records for one `(probe_id, pass_index)`, so the pair is unique, and the
    sanitised form is recorded in the index beside the identifier it came from.
    """
    safe = _UNSAFE.sub("_", probe_id).strip("._-") or "probe"
    return f"{safe}.pass{int(pass_index)}.json"


@dataclass
class SplitResult:
    """What a split produced, for the caller to report."""

    lean_path: Path
    raw_dir: Path
    index_path: Path
    source_sha256: str
    source_bytes: int
    lean_bytes: int
    #: One entry per externalised record.
    sidecars: list[dict[str, Any]] = field(default_factory=list)
    #: Records whose `raw_response` was a dict — see the module docstring.
    dict_raw_probes: list[str] = field(default_factory=list)

    @property
    def shrink_factor(self) -> float:
        return (self.source_bytes / self.lean_bytes) if self.lean_bytes else 0.0


@dataclass(frozen=True)
class JsonStyle:
    """How a JSONL file spells its records, to the byte.

    Two dimensions, because both vary in the wild and either one alone breaks the round
    trip. `write_records` emits compact separators and `ensure_ascii=False`, so a pound
    sign is a pound sign. `json.dumps` with no arguments emits spaced separators and
    escapes it to `\\u00a3` — and that is what the merge and reparse scripts beside the
    7 August captures used, which is why detecting only the separators found nothing.
    """

    separators: tuple[str, str]
    ensure_ascii: bool

    def as_record(self) -> dict[str, Any]:
        return {"separators": list(self.separators), "ensure_ascii": self.ensure_ascii}

    @classmethod
    def from_record(cls, obj: Any) -> "JsonStyle":
        if not isinstance(obj, dict):
            return DEFAULT_STYLE
        sep = obj.get("separators") or [",", ":"]
        return cls(
            separators=(str(sep[0]), str(sep[1])),
            ensure_ascii=bool(obj.get("ensure_ascii", False)),
        )


DEFAULT_STYLE = JsonStyle((",", ":"), False)

#: Every style this tool can reproduce, most likely first. Neither spelling is ours to
#: insist on — F35 says these files are written by people who are not us, and a tool that
#: only round-trips its own output would refuse the very archives that most need
#: splitting.
_STYLES: tuple[JsonStyle, ...] = (
    DEFAULT_STYLE,
    JsonStyle((", ", ": "), True),
    JsonStyle((", ", ": "), False),
    JsonStyle((",", ":"), True),
)


def _encode(record: dict[str, Any], style: JsonStyle = DEFAULT_STYLE) -> bytes:
    """One record as a JSONL line, including the newline, in the given style."""
    return (
        json.dumps(
            record,
            ensure_ascii=style.ensure_ascii,
            separators=style.separators,
        )
        + "\n"
    ).encode("utf-8")


def detect_style(path: Path) -> JsonStyle:
    """The separator style this file is written in, verified on every line.

    Sniffing the first line is not enough: the guarantee this module sells is a
    byte-exact round trip over the whole file, so the style has to hold for the whole
    file. A file that is not uniform in one of the known styles is rejected here, with
    the line that broke it, rather than at the digest comparison where the message can
    only say the totals differ.
    """
    candidates = list(_STYLES)
    with path.open("rb") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            candidates = [s for s in candidates if _encode(obj, s) == line]
            if not candidates:
                raise InterchangeError(
                    f"{path}:{lineno}: this line is not in a separator style this tool "
                    f"can reproduce byte-for-byte.\n"
                    f"  Splitting it would produce a pair that cannot be rehydrated to "
                    f"the original,\n"
                    f"  so the capture would stop being checkable. Re-emit the file "
                    f"with `jq -c` and\n"
                    f"  split that, keeping the original alongside it."
                )
    return candidates[0]


def split_response_file(
    source: str | Path,
    out_dir: str | Path,
    *,
    lean_name: str = "responses.jsonl",
    raw_dirname: str = RAW_DIRNAME,
) -> SplitResult:
    """Write a lean response file plus one raw sidecar per observation.

    Raises `InterchangeError` if the pair would not rehydrate byte-for-byte back into
    `source`. Nothing is written in that case.
    """
    src = Path(source)
    raw_bytes = src.read_bytes()
    source_sha = _digest(raw_bytes)
    style = detect_style(src)

    out = Path(out_dir)
    lean_path = out / lean_name
    raw_dir = out / raw_dirname
    if lean_path.resolve() == src.resolve():
        raise InterchangeError(
            f"{src}: refusing to split a file over itself.\n"
            f"  Choose an --output directory that is not the source's own directory,\n"
            f"  or a different --lean-name. The original is the evidence."
        )

    lean_records: list[dict[str, Any]] = []
    sidecars: list[dict[str, Any]] = []
    dict_raw: list[str] = []
    # `(probe_id, pass_index) -> sidecar filename`, so rehydration is a lookup rather
    # than a re-derivation that could drift from the naming rule above.
    written: dict[str, bytes] = {}

    for lineno, obj in read_records(src):
        if obj.get("record") == "capture_notes":
            lean_records.append(obj)
            continue

        raw = obj.get("raw_response")
        if raw is None:
            lean_records.append(obj)
            continue

        probe_id = obj.get("probe_id")
        if not isinstance(probe_id, str) or not probe_id:
            raise InterchangeError(
                f"{src}:{lineno}: record carries `raw_response` but no `probe_id`.\n"
                f"  The sidecar is named for the observation; without an identifier\n"
                f"  there is nothing to name it after."
            )
        pass_index = obj.get("pass_index", 1)
        name = sidecar_name(probe_id, pass_index)
        if name in written:
            raise InterchangeError(
                f"{src}:{lineno}: two records would write the same sidecar {name!r}.\n"
                f"  One record per (probe_id, pass_index) — repeated runs of a probe\n"
                f"  are separate passes and must increment pass_index."
            )

        if isinstance(raw, dict):
            dict_raw.append(probe_id)

        # Pretty-printed on purpose. The sidecar exists to be read by a person deciding
        # whether a finding is real, and a 900-frame stream on one line helps nobody.
        # It is never re-read for scoring, so its formatting carries no contract; the
        # value that must survive is the parsed object, and the index digests the bytes
        # so the file is still fixed.
        payload = json.dumps(raw, ensure_ascii=False, indent=2).encode("utf-8")
        written[name] = payload

        lean = dict(obj)
        lean["raw_response"] = None
        lean_records.append(lean)
        sidecars.append(
            {
                "probe_id": probe_id,
                "pass_index": pass_index,
                "file": f"{raw_dirname}/{name}",
                "sha256": _digest(payload),
                "bytes": len(payload),
                "frames": len(raw) if isinstance(raw, list) else None,
                "raw_type": type(raw).__name__,
            }
        )

    if not sidecars:
        raise InterchangeError(
            f"{src}: no record carries a `raw_response`, so there is nothing to "
            f"externalise.\n"
            f"  This file is already lean. Splitting it would only move it."
        )

    # ---- prove the round trip before writing anything -----------------------------
    # The claim this module makes is that the split is reversible. Asserting that in a
    # docstring is worth nothing; the check is cheap and the file is evidence.
    rebuilt = bytearray()
    raws = {(s["probe_id"], s["pass_index"]): s["file"] for s in sidecars}
    by_file = {f"{raw_dirname}/{n}": json.loads(p) for n, p in written.items()}
    for record in lean_records:
        if record.get("record") == "capture_notes":
            rebuilt += _encode(record, style)
            continue
        key = (record.get("probe_id"), record.get("pass_index", 1))
        restored = dict(record)
        if key in raws:
            restored["raw_response"] = by_file[raws[key]]
        rebuilt += _encode(restored, style)

    if _digest(bytes(rebuilt)) != source_sha:
        raise InterchangeError(
            f"{src}: the split would not rehydrate to the original bytes, so it was "
            f"not written.\n"
            f"  source   sha256:{source_sha}\n"
            f"  rebuilt  sha256:{_digest(bytes(rebuilt))}\n"
            f"  The usual cause is a source file not written by this tool — different\n"
            f"  JSON separators, sorted keys, or pretty-printed records. The original\n"
            f"  is untouched and remains the evidence."
        )

    # ---- write ---------------------------------------------------------------------
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in written.items():
        (raw_dir / name).write_bytes(payload)

    lean_blob = b"".join(_encode(r, style) for r in lean_records)
    lean_path.parent.mkdir(parents=True, exist_ok=True)
    lean_path.write_bytes(lean_blob)

    index = {
        "schema": "raw_index.v1",
        "source_file": src.name,
        "source_sha256": source_sha,
        "source_bytes": len(raw_bytes),
        "lean_file": lean_name,
        "lean_sha256": _digest(lean_blob),
        "lean_bytes": len(lean_blob),
        # Recorded so rehydration reproduces the source bytes rather than this
        # tool's house style. Without it a file written by someone else splits
        # fine and rehydrates to a different digest.
        "json_style": style.as_record(),
        "records": len(lean_records),
        "externalised": len(sidecars),
        "note": (
            "raw_response was moved out of the response file, one file per "
            "(probe_id, pass_index), and nulled in the record. `legal-rag-audit split "
            "--rehydrate` reverses this and reproduces source_sha256 exactly. Scoring "
            "reads raw_response only for entity_masking and only when it is an object."
        ),
        "sidecars": sidecars,
    }
    index_path = raw_dir / "index.json"
    index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return SplitResult(
        lean_path=lean_path,
        raw_dir=raw_dir,
        index_path=index_path,
        source_sha256=source_sha,
        source_bytes=len(raw_bytes),
        lean_bytes=len(lean_blob),
        sidecars=sidecars,
        dict_raw_probes=dict_raw,
    )


def rehydrate_response_file(
    lean: str | Path,
    out_path: str | Path,
    *,
    raw_dirname: str = RAW_DIRNAME,
) -> str:
    """Put the sidecars back and write the monolithic file. Returns its SHA-256.

    Reads `raw/index.json` for the mapping rather than re-deriving filenames, so a
    sidecar renamed by hand is an error that names itself instead of a record silently
    rehydrating to `null`.
    """
    lean_path = Path(lean)
    raw_dir = lean_path.parent / raw_dirname
    index_path = raw_dir / "index.json"
    if not index_path.exists():
        raise InterchangeError(
            f"{index_path}: no raw index.\n"
            f"  Rehydration needs the index written by `split`; without it there is no\n"
            f"  record of which sidecar belongs to which observation."
        )

    index = json.loads(index_path.read_text(encoding="utf-8"))
    style = JsonStyle.from_record(index.get("json_style"))
    wanted: dict[tuple[Any, Any], dict[str, Any]] = {
        (s["probe_id"], s["pass_index"]): s for s in index.get("sidecars", [])
    }

    blob = bytearray()
    restored = 0
    for _, obj in read_records(lean_path):
        if obj.get("record") == "capture_notes":
            blob += _encode(obj, style)
            continue
        key = (obj.get("probe_id"), obj.get("pass_index", 1))
        entry = wanted.get(key)
        if entry is not None:
            payload = (lean_path.parent / entry["file"]).read_bytes()
            actual = _digest(payload)
            if actual != entry["sha256"]:
                raise InterchangeError(
                    f"{entry['file']}: sidecar has changed since the split.\n"
                    f"  index sha256:{entry['sha256']}\n"
                    f"  file  sha256:{actual}\n"
                    f"  Refusing to rehydrate altered evidence."
                )
            obj = dict(obj)
            obj["raw_response"] = json.loads(payload)
            restored += 1
        blob += _encode(obj, style)

    if restored != len(wanted):
        raise InterchangeError(
            f"{lean_path}: the index names {len(wanted)} sidecars but only {restored} "
            f"records matched.\n"
            f"  The lean file and the raw directory are from different splits."
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(blob))
    return _digest(bytes(blob))


def verify_round_trip(
    lean: str | Path, *, raw_dirname: str = RAW_DIRNAME
) -> tuple[bool, str, str]:
    """Rehydrate in memory and compare against the digest the index recorded.

    Returns `(ok, expected, actual)`. Writes nothing — this is the check a reader runs
    to satisfy themselves that the split pair still reproduces the original capture.
    """
    lean_path = Path(lean)
    index_path = lean_path.parent / raw_dirname / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    expected = index["source_sha256"]

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        actual = rehydrate_response_file(
            lean_path, Path(tmp) / "rehydrated.jsonl", raw_dirname=raw_dirname
        )
    return actual == expected, expected, actual
