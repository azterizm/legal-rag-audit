"""Running one battery across several trial accounts, and joining the pieces.

The failure these guard against is not a crash. It is a merged file that looks like a
clean three-pass run and is actually three accounts stitched together — which supports a
claim about account-to-account variation and not the reproducibility claim a reader will
take from it.
"""

import json
from pathlib import Path

import pytest

from legal_rag_audit.interchange.jsonl import InterchangeError
from legal_rag_audit.interchange.segments import (
    ASSEMBLED,
    merge_segments,
    outstanding,
    write_remaining_probes,
)

HEADER = {
    "schema": "responses.v3",
    "record": "capture_notes",
    "citations_captured": False,
    "retrieved_chunks_captured": False,
}


def probe(pid, family="abstention"):
    return {
        "schema": "probes.v2",
        "probe_id": pid,
        "family": family,
        "intent": "positive",
        "text": f"question for {pid}?",
        "eligible_for": [family],
    }


def answer(pid, pass_index=1, run_id="run-a", text="an answer"):
    return {
        "schema": "responses.v3",
        "run_id": run_id,
        "probe_id": pid,
        "pass_index": pass_index,
        "query": "q",
        "answer": text,
        "error": None,
    }


def failure(pid, pass_index=1, run_id="run-a", error="HTTPStatusError: 402"):
    rec = answer(pid, pass_index, run_id, text="")
    rec["error"] = error
    return rec


def write(path: Path, records) -> Path:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


@pytest.fixture
def probes(tmp_path):
    return write(tmp_path / "probes.jsonl", [probe(f"p{i}") for i in range(1, 5)])


# ------------------------------------------------------------------ outstanding


def test_a_transport_failure_leaves_the_probe_outstanding(tmp_path, probes):
    """The whole reason an exhausted account's 402s cannot simply be merged in."""
    seg = write(tmp_path / "s1.jsonl", [HEADER, answer("p1"), failure("p2")])
    state = outstanding(probes, [seg], target_passes=1)
    assert "p1" not in state.remaining
    assert state.remaining["p2"] == 1
    assert state.gathered["p1"] == 1
    assert state.gathered["p2"] == 0


def test_the_shortfall_is_per_probe(tmp_path, probes):
    seg = write(
        tmp_path / "s1.jsonl",
        [HEADER, answer("p1", 1), answer("p1", 2), answer("p2", 1)],
    )
    state = outstanding(probes, [seg], target_passes=3)
    assert state.remaining == {"p1": 1, "p2": 2, "p3": 3, "p4": 3}
    assert state.next_passes == 3
    assert not state.complete


def test_passes_accumulate_across_segments(tmp_path, probes):
    a = write(tmp_path / "a.jsonl", [HEADER, answer("p1", 1, "run-a")])
    b = write(tmp_path / "b.jsonl", [HEADER, answer("p1", 1, "run-b")])
    state = outstanding(probes, [a, b], target_passes=2)
    assert "p1" not in state.remaining


def test_a_complete_battery_reports_nothing_outstanding(tmp_path, probes):
    seg = write(tmp_path / "s.jsonl", [HEADER] + [answer(f"p{i}") for i in range(1, 5)])
    state = outstanding(probes, [seg], target_passes=1)
    assert state.complete
    with pytest.raises(InterchangeError, match="Nothing is outstanding"):
        write_remaining_probes(probes, tmp_path / "rest.jsonl", state)


def test_probe_ids_from_another_battery_are_reported_not_counted(tmp_path, probes):
    seg = write(tmp_path / "s.jsonl", [HEADER, answer("pit-era-124-1")])
    state = outstanding(probes, [seg], target_passes=1)
    assert state.unknown == ["pit-era-124-1"]
    assert len(state.remaining) == 4


def test_the_remaining_file_preserves_battery_order(tmp_path):
    """Abstention was moved to the front on purpose; a segment must not undo that."""
    ordered = write(
        tmp_path / "probes.jsonl",
        [probe("fict-a"), probe("fict-b"), probe("pit-a", "point_in_time")],
    )
    seg = write(tmp_path / "s.jsonl", [HEADER, answer("fict-b")])
    state = outstanding(ordered, [seg], target_passes=1)
    written = write_remaining_probes(ordered, tmp_path / "rest.jsonl", state)
    assert written == 2
    ids = [json.loads(l)["probe_id"] for l in open(tmp_path / "rest.jsonl")]
    assert ids == ["fict-a", "pit-a"]


# ----------------------------------------------------------------------- merge


def test_a_failure_superseded_by_a_later_answer_is_dropped(tmp_path):
    a = write(tmp_path / "a.jsonl", [HEADER, answer("p1"), failure("p2")])
    b = write(tmp_path / "b.jsonl", [HEADER, answer("p2", run_id="run-b")])
    summary = merge_segments([a, b], tmp_path / "m.jsonl")
    assert summary["dropped_superseded"] == 1
    rows = [json.loads(l) for l in open(tmp_path / "m.jsonl")][1:]
    assert {r["probe_id"] for r in rows} == {"p1", "p2"}
    assert all(r["error"] is None for r in rows)


def test_an_unanswered_probe_keeps_one_failure_record(tmp_path):
    """It must stay in the denominator as NOT_CAPTURED, not vanish."""
    a = write(tmp_path / "a.jsonl", [HEADER, failure("p1")])
    b = write(tmp_path / "b.jsonl", [HEADER, failure("p1", run_id="run-b")])
    merge_segments([a, b], tmp_path / "m.jsonl")
    rows = [json.loads(l) for l in open(tmp_path / "m.jsonl")][1:]
    assert len(rows) == 1 and rows[0]["error"]


def test_pass_index_is_renumbered_so_the_file_is_readable(tmp_path):
    """Two accounts each running --passes 1 both produce pass_index 1."""
    from legal_rag_audit.interchange.response import load_responses

    a = write(tmp_path / "a.jsonl", [HEADER, answer("p1", 1, "run-a")])
    b = write(tmp_path / "b.jsonl", [HEADER, answer("p1", 1, "run-b")])
    merge_segments([a, b], tmp_path / "m.jsonl")
    parsed = load_responses(tmp_path / "m.jsonl")
    assert sorted(r.pass_index for r in parsed.responses) == [1, 2]
    # The run_id is what lets a reader take the merge apart again.
    assert {r.run_id for r in parsed.responses} == {"run-a", "run-b"}


def test_the_header_says_the_file_was_assembled(tmp_path):
    a = write(tmp_path / "a.jsonl", [HEADER, answer("p1")])
    b = write(tmp_path / "b.jsonl", [HEADER, answer("p2")])
    merge_segments([a, b], tmp_path / "m.jsonl", note="two trial accounts.")
    header = json.loads(open(tmp_path / "m.jsonl").readline())
    assert "ASSEMBLED FROM 2 SEGMENTS" in header["notes"]
    assert "reproducibility" in header["notes"]
    assert header["notes"].endswith("two trial accounts.")


def test_the_assembly_warning_cannot_be_replaced_by_the_operators_note(tmp_path):
    a = write(tmp_path / "a.jsonl", [HEADER, answer("p1")])
    b = write(tmp_path / "b.jsonl", [HEADER, answer("p2")])
    merge_segments([a, b], tmp_path / "m.jsonl", note="one clean run, honest.")
    notes = json.loads(open(tmp_path / "m.jsonl").readline())["notes"]
    assert notes.startswith(ASSEMBLED.format(n=2))


def test_a_single_segment_is_refused(tmp_path):
    a = write(tmp_path / "a.jsonl", [HEADER, answer("p1")])
    with pytest.raises(InterchangeError, match="at least two"):
        merge_segments([a], tmp_path / "m.jsonl")


def test_a_merge_with_no_header_anywhere_is_refused(tmp_path):
    a = write(tmp_path / "a.jsonl", [answer("p1")])
    b = write(tmp_path / "b.jsonl", [answer("p2")])
    with pytest.raises(InterchangeError, match="capture_notes"):
        merge_segments([a, b], tmp_path / "m.jsonl")


def test_the_merged_file_scores(tmp_path):
    """End to end: two quota-limited accounts produce one readable response file."""
    from legal_rag_audit.interchange.response import load_responses

    a = write(tmp_path / "a.jsonl", [HEADER, answer("p1"), failure("p2")])
    b = write(tmp_path / "b.jsonl", [HEADER, answer("p2", run_id="run-b"), answer("p3", run_id="run-b")])
    summary = merge_segments([a, b], tmp_path / "m.jsonl")
    parsed = load_responses(tmp_path / "m.jsonl")
    assert summary["answered"] == 3
    assert len(parsed.responses) == 3
    assert parsed.capture_notes is not None
    assert "ASSEMBLED" in parsed.capture_notes.notes
