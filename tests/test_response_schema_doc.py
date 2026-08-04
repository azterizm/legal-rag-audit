"""The worked example in `docs/responses-schema.md` is executed, not just published.

F35 says a competent engineer produces a conforming `responses.jsonl` from the spec
alone, running none of our code. The only honest way to keep that true is to run the
spec's own example and score the file it produces — a documented pipeline nobody
executes is a pipeline that stopped working at some commit nobody noticed.

The script is extracted from the Markdown rather than copied into this file. A copy
would pass forever while the document rotted.

The stub server here is deliberately trivial: it exists to prove the *transport and
format* round-trip, not to exhibit any pathology. The pathological reference target with
its nineteen failure modes is §14.1, and arrives in Phase F2.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from legal_rag_audit.interchange import load_responses
from legal_rag_audit.probes import build_ground_truth, build_probes
from legal_rag_audit.interchange import write_ground_truth, write_probes

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "responses-schema.md"


def extract_bash_blocks(markdown: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", markdown, flags=re.DOTALL)


def the_worked_example() -> str:
    """The one block that builds the response file."""
    blocks = [b for b in extract_bash_blocks(DOC.read_text(encoding="utf-8")) if "while read" in b]
    assert len(blocks) == 1, (
        f"expected exactly one worked example in {DOC.name}, found {len(blocks)}"
    )
    return blocks[0]


class _Handler(BaseHTTPRequestHandler):
    """Answers anything with a fixed shape. No pathology, no opinions."""

    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        body = json.dumps(
            {
                "answer": f"Stub answer to: {payload.get('query', '')}",
                "sources": ["doc_1"],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # keep pytest output readable
        pass


@pytest.fixture
def stub_target():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.slow
def test_the_documented_curl_example_produces_a_conforming_file(stub_target, tmp_path):
    if shutil.which("jq") is None:  # pragma: no cover - environment dependent
        pytest.skip("jq is not installed; the documented example needs it")
    if shutil.which("curl") is None:  # pragma: no cover
        pytest.skip("curl is not installed; the documented example needs it")

    write_probes(tmp_path / "probes.jsonl", build_probes())
    (tmp_path / "document_ids.json").write_text('["doc_1","doc_2"]', encoding="utf-8")

    script = the_worked_example()
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "TARGET_URL": stub_target,
            "TARGET_API_KEY": "not-a-real-key",
        },
    )
    assert result.returncode == 0, (
        f"the documented example failed:\n{result.stdout}\n{result.stderr}"
    )

    # The real assertion: our own loader accepts what the documented pipeline wrote.
    parsed = load_responses(tmp_path / "responses.jsonl")
    assert len(parsed.responses) == len(build_probes())
    assert parsed.capture_notes is not None
    assert parsed.capture_notes.document_ids == ["doc_1", "doc_2"]
    assert parsed.citations_captured() is True
    assert parsed.retrieved_chunks_captured() is False
    assert all(r.answer for r in parsed.responses)
    assert all(r.usable for r in parsed.responses)


@pytest.mark.slow
def test_a_file_from_the_documented_example_scores(stub_target, tmp_path):
    """End to end: doc-produced file in, report out, no network on the scoring side."""
    if shutil.which("jq") is None or shutil.which("curl") is None:  # pragma: no cover
        pytest.skip("the documented example needs curl and jq")

    write_probes(tmp_path / "probes.jsonl", build_probes())
    write_ground_truth(tmp_path / "ground_truth.json", build_ground_truth())
    (tmp_path / "document_ids.json").write_text('["doc_1","doc_2"]', encoding="utf-8")

    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", the_worked_example()],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "TARGET_URL": stub_target, "TARGET_API_KEY": "x"},
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "legal_rag_audit.cli",
            "score",
            "--responses",
            str(tmp_path / "responses.jsonl"),
            "--ground-truth",
            str(tmp_path / "ground_truth.json"),
            "--probes",
            str(tmp_path / "probes.jsonl"),
            "--skip-tier2",
            "-o",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    # The stub answers every probe with the same sentence, so findings are expected.
    # What is being asserted is that it *ran*: exit 2 would mean it could not.
    assert result.returncode in (0, 1), f"{result.stdout}\n{result.stderr}"

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["checks_registered"] == 18
    assert report["capture"]["eligibility_source"] == "probe file"
    # Chunks were never captured by the documented pipeline, so the check that reads
    # them must say so rather than pass.
    assert report["checks"]["retrieval_relevance"]["status"] == "NOT_CAPTURED"


def test_the_doc_states_the_null_versus_empty_rule():
    """The distinction the whole degradation model rests on has to be in the spec."""
    text = DOC.read_text(encoding="utf-8")
    assert "`null` and `[]` are different facts" in text
    assert "NOT_CAPTURED" in text


def test_score_reads_the_response_file_before_the_ground_truth(tmp_path):
    """The doc tells people to check their file with a bogus --ground-truth.

    That advice only holds if the response file is parsed first; otherwise they get an
    error about the manifest and learn nothing about the file they came to check.
    """
    from legal_rag_audit.interchange import InterchangeError
    from legal_rag_audit.score import score

    bad = tmp_path / "responses.jsonl"
    bad.write_text('{"schema":"responses.v2","run_id":"r"}\n', encoding="utf-8")

    with pytest.raises(InterchangeError) as excinfo:
        score(str(bad), os.devnull, skip_tier2=True)

    message = str(excinfo.value)
    assert "responses.jsonl" in message
    assert ":1:" in message, "the error must name the line the producer has to fix"
