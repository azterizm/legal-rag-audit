"""The interchange contracts hold, and refuse what they cannot honestly read.

Strangers write `responses.jsonl` (F35), so every failure mode here is one somebody
will hit at their own desk. The tests are about what the error *says* as much as that
there is one.
"""

import json
import zipfile
from pathlib import Path

import pytest

from legal_rag_audit.interchange import (
    CaptureNotes,
    GroundTruth,
    InterchangeError,
    Probe,
    Response,
    SchemaVersionError,
    available_schemas,
    load_ground_truth,
    load_probes,
    load_responses,
    read_schema_document,
    write_ground_truth,
    write_probes,
    write_responses,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_lines(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


RESPONSE = (
    '{"schema":"responses.v2","run_id":"r","probe_id":"p1","query":"q","answer":"a"}'
)


# ------------------------------------------------------------------ version refusal


def test_unknown_schema_version_is_refused_not_parsed(tmp_path):
    """NF10. A guessed reading of an unknown version is indistinguishable from a
    correct one in the report it produces, which is why there is no best-effort path."""
    path = write_lines(tmp_path / "r.jsonl", RESPONSE.replace("v2", "v9"))
    with pytest.raises(SchemaVersionError) as e:
        load_responses(path)
    assert "responses.v9" in str(e.value)
    assert "Refusing" in str(e.value)


def test_a_superseded_version_is_refused_and_told_what_replaced_it(tmp_path):
    """Still refused — but somebody holding a v1 file learns why it moved.

    The alternative is a correct refusal that reads as a bug: the file was valid when it
    was written, and *"expected responses.v2"* on its own does not say that.
    """
    path = write_lines(tmp_path / "r.jsonl", RESPONSE.replace("v2", "v1"))
    with pytest.raises(SchemaVersionError) as e:
        load_responses(path)
    message = str(e.value)
    assert "superseded by responses.v2" in message
    assert "revision_wait_seconds" in message, "say what changed, not just that it did"


def test_a_missing_schema_field_is_refused(tmp_path):
    path = write_lines(tmp_path / "r.jsonl", '{"run_id":"r","probe_id":"p","query":"q","answer":"a"}')
    with pytest.raises(SchemaVersionError, match="no `schema` field"):
        load_responses(path)


def test_ground_truth_version_is_refused_too(tmp_path):
    path = tmp_path / "gt.json"
    path.write_text('{"schema":"ground_truth.v0","expectations":[]}', encoding="utf-8")
    with pytest.raises(SchemaVersionError):
        load_ground_truth(path)


# ------------------------------------------------------------------- error messages


def test_a_parse_error_names_the_line(tmp_path):
    path = write_lines(tmp_path / "r.jsonl", RESPONSE, "{not json}", RESPONSE)
    with pytest.raises(InterchangeError) as e:
        load_responses(path)
    assert ":2:" in str(e.value)


def test_a_multiline_object_is_diagnosed_with_the_fix(tmp_path):
    """The single most common way this file comes back wrong."""
    path = tmp_path / "r.jsonl"
    path.write_text('{\n  "schema": "responses.v2"\n}\n', encoding="utf-8")
    with pytest.raises(InterchangeError, match="jq -c"):
        load_responses(path)


def test_an_unknown_field_points_at_raw_response(tmp_path):
    path = write_lines(
        tmp_path / "r.jsonl",
        '{"schema":"responses.v2","run_id":"r","probe_id":"p","query":"q",'
        '"answer":"a","latency":5}',
    )
    with pytest.raises(InterchangeError) as e:
        load_responses(path)
    assert "latency" in str(e.value)
    assert "raw_response" in str(e.value)


def test_an_empty_file_is_a_setup_problem_not_an_empty_result(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(InterchangeError, match="no records"):
        load_responses(path)


def test_duplicate_probe_and_pass_is_refused(tmp_path):
    path = write_lines(tmp_path / "r.jsonl", RESPONSE, RESPONSE)
    with pytest.raises(InterchangeError, match="duplicate record"):
        load_responses(path)


def test_the_same_probe_at_a_different_pass_is_fine(tmp_path):
    path = write_lines(
        tmp_path / "r.jsonl",
        RESPONSE,
        RESPONSE.replace('"answer":"a"', '"answer":"b","pass_index":2'),
    )
    assert len(load_responses(path).responses) == 2


def test_duplicate_probe_ids_are_refused(tmp_path):
    line = (
        '{"schema":"probes.v2","probe_id":"p","family":"f","intent":"positive",'
        '"text":"t","eligible_for":["c"]}'
    )
    path = write_lines(tmp_path / "p.jsonl", line, line)
    with pytest.raises(InterchangeError, match="duplicate probe_id"):
        load_probes(path)


def test_two_expectations_for_one_probe_and_check_are_refused(tmp_path):
    path = tmp_path / "gt.json"
    path.write_text(
        json.dumps(
            {
                "schema": "ground_truth.v2",
                "expectations": [
                    {"probe_id": "p", "check": "c"},
                    {"probe_id": "p", "check": "c"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(InterchangeError, match="two expectations"):
        load_ground_truth(path)


# ------------------------------------------------------------- capture-notes header


def test_capture_notes_must_come_first(tmp_path):
    notes = (
        '{"schema":"responses.v2","record":"capture_notes",'
        '"citations_captured":true,"retrieved_chunks_captured":true}'
    )
    path = write_lines(tmp_path / "r.jsonl", RESPONSE, notes)
    with pytest.raises(InterchangeError, match="must be the first record"):
        load_responses(path)


def test_declared_capture_beats_inference(tmp_path):
    """A header saying 'we did not capture citations' is believed over the records.

    Every record here carries citations: null. Without the header that is ambiguous —
    the system may emit none, or nothing may have looked. The producer knows; we do not.
    """
    notes = (
        '{"schema":"responses.v2","record":"capture_notes",'
        '"citations_captured":false,"retrieved_chunks_captured":false}'
    )
    parsed = load_responses(write_lines(tmp_path / "r.jsonl", notes, RESPONSE))
    assert parsed.citations_captured() is False


def test_absent_header_leaves_capture_unknown_rather_than_assumed(tmp_path):
    parsed = load_responses(write_lines(tmp_path / "r.jsonl", RESPONSE))
    assert parsed.citations_captured() is None
    assert parsed.retrieved_chunks_captured() is None


def test_an_empty_citation_list_is_a_captured_result(tmp_path):
    path = write_lines(
        tmp_path / "r.jsonl", RESPONSE.replace('"answer":"a"', '"answer":"a","citations":[]')
    )
    parsed = load_responses(path)
    assert parsed.citations_captured() is True
    assert parsed.responses[0].citations == []


# ------------------------------------------------------------------------ semantics


def test_a_record_with_an_error_is_not_usable(tmp_path):
    path = write_lines(
        tmp_path / "r.jsonl",
        RESPONSE.replace('"answer":"a"', '"answer":"","error":"ReadTimeout"'),
    )
    assert load_responses(path).responses[0].usable is False


def test_an_explicit_record_response_is_accepted_and_not_echoed_back(tmp_path):
    """`record` is a discriminator, not data. §6.3's example omits it."""
    path = write_lines(
        tmp_path / "r.jsonl", RESPONSE.replace('"run_id"', '"record":"response","run_id"')
    )
    parsed = load_responses(path)
    assert "record" not in parsed.responses[0].to_record()


def test_an_unknown_record_type_is_refused(tmp_path):
    path = write_lines(
        tmp_path / "r.jsonl", '{"schema":"responses.v2","record":"summary"}'
    )
    with pytest.raises(InterchangeError, match="unknown record type"):
        load_responses(path)


# ------------------------------------------------------------------- round-tripping


def test_probes_round_trip(tmp_path):
    original = [
        Probe(
            probe_id="p1",
            family="f",
            intent="no_correct_answer",
            text="t",
            eligible_for=["a", "b"],
            passes=3,
        )
    ]
    path = tmp_path / "p.jsonl"
    write_probes(path, original)
    assert load_probes(path) == original


def test_responses_round_trip(tmp_path):
    original = [
        Response(
            run_id="r",
            probe_id="p1",
            query="q",
            answer="a",
            citations=["d1"],
            total_ms=12,
        )
    ]
    notes = CaptureNotes(
        record="capture_notes",
        citations_captured=True,
        retrieved_chunks_captured=False,
        document_ids=["d1"],
    )
    path = tmp_path / "r.jsonl"
    write_responses(path, original, notes)
    parsed = load_responses(path)
    assert parsed.responses == original
    assert parsed.capture_notes == notes


def test_ground_truth_round_trips(tmp_path):
    from legal_rag_audit.interchange import Expectation

    original = GroundTruth(
        expectations=[
            Expectation(probe_id="p1", check="c", must_not_contain=["x"]),
        ]
    )
    path = tmp_path / "gt.json"
    write_ground_truth(path, original)
    assert load_ground_truth(path) == original


def test_written_records_are_one_line_each(tmp_path):
    path = tmp_path / "r.jsonl"
    write_responses(
        path, [Response(run_id="r", probe_id=f"p{i}", query="q", answer="a") for i in range(5)]
    )
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 5


# ----------------------------------------------------------------- published schemas


def test_published_schemas_match_the_models():
    """The contract a third party validates against is generated from what we accept.

    Hand-maintaining both guarantees drift, and a published spec that score would
    reject is worse than none — it sends someone away to build the wrong thing.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_schemas.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_supported_version_has_a_published_schema():
    for version in available_schemas():
        document = read_schema_document(version)
        assert document["$schema"].startswith("https://json-schema.org/")
        assert "schema" in document.get("required", []) or "oneOf" in document


def test_the_schema_requires_the_version_declaration():
    """The loaders refuse a record with no `schema`; the published contract says so too."""
    for version in ("probes.v2", "ground_truth.v2"):
        assert "schema" in read_schema_document(version)["required"]
    for variant in read_schema_document("responses.v2")["oneOf"]:
        assert "schema" in variant["required"]


def test_unpublished_version_is_refused():
    with pytest.raises(SchemaVersionError, match="No published schema"):
        read_schema_document("responses.v99")


@pytest.mark.slow
def test_schemas_ship_in_the_built_wheel(tmp_path):
    """`schema --print` has to work from an installed wheel, or F35 needs a git clone."""
    import shutil
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # pragma: no cover - environment dependent
        pytest.skip(f"wheel build unavailable:\n{result.stderr[-400:]}")

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as zf:
        shipped = {
            Path(n).name
            for n in zf.namelist()
            if "interchange/jsonschema/" in n and n.endswith(".json")
        }
    assert shipped == {f"{v}.schema.json" for v in available_schemas()}
    assert shutil  # silence the unused import in the skip path
