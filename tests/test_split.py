"""`split` — the round trip is the whole contract, so it is what these test.

A response file is evidence. Externalising part of it is only safe if the original can
be reproduced from the pair, which is why `split_response_file` proves the round trip
before it writes and refuses when it cannot. These tests hold that guarantee against the
shapes that actually occur: our own compact output, the spaced-and-escaped output of the
scripts that produced the August captures, records with no raw payload at all, and the
non-ASCII figures the whole battery is built out of.
"""

import json
from pathlib import Path

import pytest

from legal_rag_audit.interchange.jsonl import InterchangeError
from legal_rag_audit.interchange.split import (
    JsonStyle,
    detect_style,
    rehydrate_response_file,
    sidecar_name,
    split_response_file,
    verify_round_trip,
)

HEADER = {
    "schema": "responses.v3",
    "record": "capture_notes",
    "citations_captured": False,
    "retrieved_chunks_captured": False,
}


def _record(probe_id, pass_index=1, raw=None, answer="an answer"):
    return {
        "schema": "responses.v3",
        "run_id": "run-1",
        "probe_id": probe_id,
        "pass_index": pass_index,
        "query": "As at 1 January 2012, what was the maximum compensatory award?",
        "answer": answer,
        "raw_response": raw,
    }


def _write(path: Path, records, style: JsonStyle) -> Path:
    with path.open("wb") as fh:
        for r in records:
            fh.write(
                (
                    json.dumps(
                        r,
                        ensure_ascii=style.ensure_ascii,
                        separators=style.separators,
                    )
                    + "\n"
                ).encode("utf-8")
            )
    return path


# The two spellings that matter: `write_records`, and `json.dumps` with no arguments —
# which is what the merge and reparse scripts beside the captures used.
STYLES = [
    JsonStyle((",", ":"), False),
    JsonStyle((", ", ": "), True),
]


@pytest.mark.parametrize("style", STYLES, ids=["compact", "spaced-escaped"])
def test_round_trip_is_byte_identical(tmp_path, style):
    src = _write(
        tmp_path / "responses.jsonl",
        [
            HEADER,
            _record("pit-era-124-1", raw=[{"type": "text_end", "content": "£68,400"}]),
            _record("pit-era-124-2", raw=[{"type": "text_end", "content": "£74,200"}]),
        ],
        style,
    )
    original = src.read_bytes()

    result = split_response_file(src, tmp_path / "out")
    assert result.lean_bytes < result.source_bytes

    back = tmp_path / "back.jsonl"
    rehydrate_response_file(result.lean_path, back)
    assert back.read_bytes() == original


@pytest.mark.parametrize("style", STYLES, ids=["compact", "spaced-escaped"])
def test_detect_style_recovers_the_spelling(tmp_path, style):
    src = _write(tmp_path / "r.jsonl", [HEADER, _record("p1", raw=[1, 2])], style)
    assert detect_style(src) == style


def test_pound_signs_survive_both_spellings(tmp_path):
    """The battery is made of `£68,400`. An escaping change would corrupt every anchor."""
    for style in STYLES:
        src = _write(
            tmp_path / f"r-{style.ensure_ascii}.jsonl",
            [_record("p1", raw=[{"answer": "£68,400 and £74,200 — not £72,300"}])],
            style,
        )
        out = tmp_path / f"out-{style.ensure_ascii}"
        result = split_response_file(src, out)
        payload = json.loads((result.raw_dir / "p1.pass1.json").read_text("utf-8"))
        assert payload[0]["answer"] == "£68,400 and £74,200 — not £72,300"
        assert verify_round_trip(result.lean_path)[0]


def test_lean_file_nulls_raw_but_keeps_everything_else(tmp_path):
    src = _write(
        tmp_path / "r.jsonl",
        [HEADER, _record("p1", raw=[{"big": "x" * 5000}], answer="kept")],
        STYLES[0],
    )
    result = split_response_file(src, tmp_path / "out")

    lines = result.lean_path.read_text("utf-8").splitlines()
    record = json.loads(lines[1])
    assert record["raw_response"] is None
    assert record["answer"] == "kept"
    assert record["probe_id"] == "p1"
    # The header is preserved verbatim — it declares what the run could capture, and a
    # split that dropped it would silently disable checks at scoring time.
    assert json.loads(lines[0])["record"] == "capture_notes"


def test_records_without_raw_are_passed_through(tmp_path):
    src = _write(
        tmp_path / "r.jsonl",
        [_record("p1", raw=[{"a": 1}]), _record("p2", raw=None)],
        STYLES[0],
    )
    result = split_response_file(src, tmp_path / "out")
    assert len(result.sidecars) == 1
    assert not (result.raw_dir / "p2.pass1.json").exists()
    assert verify_round_trip(result.lean_path)[0]


def test_one_sidecar_per_pass(tmp_path):
    src = _write(
        tmp_path / "r.jsonl",
        [_record("p1", pass_index=i, raw=[{"pass": i}]) for i in (1, 2, 3)],
        STYLES[0],
    )
    result = split_response_file(src, tmp_path / "out")
    assert len(result.sidecars) == 3
    for i in (1, 2, 3):
        payload = json.loads((result.raw_dir / f"p1.pass{i}.json").read_text("utf-8"))
        assert payload[0]["pass"] == i


def test_file_with_nothing_to_externalise_is_refused(tmp_path):
    src = _write(tmp_path / "r.jsonl", [_record("p1", raw=None)], STYLES[0])
    with pytest.raises(InterchangeError, match="already lean"):
        split_response_file(src, tmp_path / "out")


def test_unreproducible_spelling_is_refused_before_writing(tmp_path):
    """A pretty-printed or otherwise unknown spelling must abort, not silently mangle."""
    src = tmp_path / "r.jsonl"
    src.write_text(
        json.dumps(_record("p1", raw=[{"a": 1}]), indent=None, separators=(" , ", " : "))
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(InterchangeError, match="separator style"):
        split_response_file(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_refuses_to_overwrite_the_source(tmp_path):
    src = _write(tmp_path / "responses.jsonl", [_record("p1", raw=[1])], STYLES[0])
    with pytest.raises(InterchangeError, match="over itself"):
        split_response_file(src, tmp_path)


def test_altered_sidecar_refuses_to_rehydrate(tmp_path):
    """The digest in the index is what makes the archive evidence rather than a copy."""
    src = _write(tmp_path / "r.jsonl", [_record("p1", raw=[{"a": 1}])], STYLES[0])
    result = split_response_file(src, tmp_path / "out")

    (result.raw_dir / "p1.pass1.json").write_text('[{"a": 999}]', encoding="utf-8")
    with pytest.raises(InterchangeError, match="changed since the split"):
        rehydrate_response_file(result.lean_path, tmp_path / "back.jsonl")


def test_index_records_digests_and_style(tmp_path):
    src = _write(tmp_path / "r.jsonl", [_record("p1", raw=[{"a": 1}])], STYLES[1])
    result = split_response_file(src, tmp_path / "out")

    index = json.loads(result.index_path.read_text("utf-8"))
    assert index["source_sha256"] == result.source_sha256
    assert index["json_style"] == {"separators": [", ", ": "], "ensure_ascii": True}
    entry = index["sidecars"][0]
    assert entry["probe_id"] == "p1"
    assert entry["frames"] == 1
    assert entry["sha256"] == __import__("hashlib").sha256(
        (result.raw_dir / "p1.pass1.json").read_bytes()
    ).hexdigest()


def test_sidecar_name_is_filesystem_safe():
    """`probe_id` comes from a file someone else may have written (F35)."""
    assert sidecar_name("../../etc/passwd", 1) == "etc_passwd.pass1.json"
    assert "/" not in sidecar_name("a/b/c", 2)
    assert sidecar_name("pit-era-124-1", 3) == "pit-era-124-1.pass3.json"


def test_scoring_reads_the_lean_file_the_same_way(tmp_path):
    """The claim that justifies splitting: `score` ignores a list-shaped raw_response."""
    from legal_rag_audit.interchange.response import load_responses

    src = _write(
        tmp_path / "r.jsonl",
        [HEADER, _record("p1", raw=[{"type": "text_end", "content": "x"} for _ in range(50)])],
        STYLES[0],
    )
    result = split_response_file(src, tmp_path / "out")

    before = load_responses(src)
    after = load_responses(result.lean_path)
    assert [r.answer for r in before.responses] == [r.answer for r in after.responses]
    assert [r.probe_id for r in before.responses] == [r.probe_id for r in after.responses]
    assert after.responses[0].raw_response is None
