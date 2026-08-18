"""`validate` — Phase F. Three neutral probes, and a named diagnosis for each §7.1 row.

Two kinds of test here, and the first kind is the one that matters most.

**The battery must not leak.** §7.1's warning is that `validate` prints raw response
bodies to the target's terminal, so a canary or an injection payload reaching this mode
gives the product away. That is asserted three ways: the import graph is walked (no edge
to `probes`, `plants` or `corpus_loader`), the neutral material is checked against every
value a real planting mints, and the rendered output of a live run is checked against the
same set. A convention would have been cheaper and would not have survived the first
person who wanted to reuse a probe.

**Every condition in §7.1's table produces a diagnosis rather than a stack trace.** One
test per row, each against a stub target configured to misbehave in exactly that way.
The assertion is on the diagnosis *code* rather than on its prose, so the wording stays
editable and the contract does not.
"""

import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from legal_rag_audit.config import AuditConfig
from legal_rag_audit.validate import (
    BATTERY_PROBE_COUNT,
    NEUTRAL_PROBES,
    render,
    validate,
)
from legal_rag_audit.validate.neutral import (
    NEUTRAL_DOCUMENT_FILENAME,
    NEUTRAL_DOCUMENT_TEXT,
)
from legal_rag_audit.validate.suggest import answer_candidates, citation_candidates
from test_offline_scoring import reachable_from

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------- the stub target


class _Handler(BaseHTTPRequestHandler):
    """One handler, many pathologies. `self.server.mode` selects."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def handle_one_request(self):
        # Abandoning a stream mid-flight is the behaviour under test, and on a
        # keep-alive connection it surfaces here as a reset on the *next* request line.
        # Swallowed so the stub's noise does not look like the harness misbehaving.
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def _send(self, status: int, body: bytes, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        mode = self.server.mode

        if self.path.endswith("/documents"):
            if mode == "upload_no_id":
                return self._send(200, json.dumps({"status": "stored"}).encode())
            return self._send(200, json.dumps({"id": "doc-1"}).encode())

        if mode == "auth":
            return self._send(401, json.dumps({"error": "invalid token"}).encode())
        if mode == "rate_limit":
            return self._send(429, json.dumps({"error": "slow down"}).encode())
        if mode == "rate_limit_retry":
            body = json.dumps({"error": "slow down"}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "30")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if mode == "server_error":
            return self._send(500, json.dumps({"error": "boom"}).encode())
        if mode == "slow":
            time.sleep(self.server.delay)
        if mode == "wrong_path":
            body = {
                "result": {
                    "message": "The Companies Act 2006 consolidated most of the "
                    "previous company law statutes into a single instrument.",
                    "request_id": "abc-123",
                },
                "documents": [{"ref": "d1", "title": "A"}, {"ref": "d2", "title": "B"}],
            }
            return self._send(200, json.dumps(body).encode())
        if mode == "sse_forever":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                for index in range(2000):
                    frame = json.dumps({"delta": f"word{index} "})
                    self.wfile.write(f"data: {frame}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        if mode == "sse_clean":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                for word in ("This ", "system ", "searches ", "documents."):
                    frame = json.dumps({"delta": word, "sources": ["d1"]})
                    self.wfile.write(f"data: {frame}\n\n".encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return

        payload = json.loads(raw or b"{}")
        body = {
            "response": {
                "text": f"This system answers questions about documents. You asked: "
                f"{payload.get('query', '')}",
                "sources": ["d1", "d2"],
            }
        }
        return self._send(200, json.dumps(body).encode())

    def do_GET(self):  # noqa: N802
        body = {"data": [{"content": "a chunk", "doc_id": "d1"}]}
        return self._send(200, json.dumps(body).encode())


def _serve(mode: str, delay: float = 0.0):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.mode = mode
    server.delay = delay
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def target():
    """A stub whose pathology is chosen per test."""
    servers = []

    def make(mode="clean", delay=0.0):
        server = _serve(mode, delay)
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}"

    yield make
    for server in servers:
        server.shutdown()
        server.server_close()


def config_for(url: str, **overrides) -> AuditConfig:
    response_format = {
        "answer_field": "response.text",
        "citations_field": "response.sources",
    }
    response_format.update(overrides.pop("response_format", {}))
    document = {
        "target": {
            "name": "stub",
            "endpoints": {"chat": f"{url}/chat", "upload": f"{url}/documents"},
            "response_format": response_format,
        }
    }
    document["target"].update(overrides.pop("target", {}))
    document.update(overrides)
    return AuditConfig(**document)


# ------------------------------------------------- the battery must not leak (§7.1)

#: Everything the warning in §7.1 is about. `probes` holds the questions, `plants` mints
#: the canaries and the injection payloads, `corpus_loader` reads the documents they sit
#: in, and the evaluators name what each one is for.
FORBIDDEN = ("probes", "plants", "corpus_loader", "evaluators", "score")


def test_validate_cannot_reach_the_battery():
    reachable = reachable_from("legal_rag_audit.validate")
    offenders = {
        module
        for module in reachable
        for part in FORBIDDEN
        if module.startswith(f"legal_rag_audit.{part}")
    }
    assert not offenders, (
        f"the validate package imports {offenders}. §7.1 makes non-leakage a property "
        f"of what this package can reach, not of how carefully it is written — its raw "
        f"output is printed to the target's terminal."
    )


def test_the_neutral_material_contains_no_planted_value():
    """Every invariant a real planting mints, checked against everything we print."""
    from legal_rag_audit.plants import plant

    corpus = plant("leak-check-seed")
    minted = {p.value for p in corpus.plants if getattr(p, "value", None)}
    assert minted, "the planting produced no values, so this test proves nothing"

    surface = " ".join(
        [p.text for p in NEUTRAL_PROBES]
        + [p.purpose for p in NEUTRAL_PROBES]
        + [NEUTRAL_DOCUMENT_TEXT, NEUTRAL_DOCUMENT_FILENAME]
    )
    for value in minted:
        assert value not in surface


def test_a_live_run_prints_no_planted_value(target):
    from legal_rag_audit.plants import plant

    corpus = plant("leak-check-seed")
    minted = {p.value for p in corpus.plants if getattr(p, "value", None)}

    result = validate(config_for(target()), timeout=5.0)
    printed = render(result)
    for value in minted:
        assert value not in printed


def test_the_projection_constant_tracks_the_real_battery():
    """A number rather than an import (§7.1), so the build has to keep it honest.

    If this fails, the battery changed size and `BATTERY_PROBE_COUNT` did not. Update
    the constant — do not import `build_probes` into the validate package to compute it,
    which is the edge the test above forbids.
    """
    from legal_rag_audit.probes import build_probes

    assert BATTERY_PROBE_COUNT == len(build_probes())


def test_validate_writes_nothing(target, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    validate(config_for(target()), timeout=5.0)
    assert list(tmp_path.iterdir()) == [], (
        "§7.1 says nothing is written. A stranger running the free pre-sale check "
        "should not find a file in the directory afterwards."
    )


def test_the_cli_writes_no_log_file_under_validate(target, tmp_path):
    """The log handler is the one file `validate` could still leave behind."""
    url = target()
    config = tmp_path / "config.yaml"
    config.write_text(
        "target:\n"
        "  name: stub\n"
        "  endpoints:\n"
        f"    chat: {url}/chat\n"
        f"    upload: {url}/documents\n"
        "  response_format:\n"
        "    answer_field: response.text\n"
        "    citations_field: response.sources\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "legal_rag_audit.cli", "validate", "-c", str(config)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".legal_rag_audit.log").exists()


# ------------------------------------------------------------ the happy path

def test_a_working_target_produces_no_diagnoses(target):
    result = validate(config_for(target()), timeout=5.0)
    assert [d.code for d in result.diagnoses] == []
    assert result.blocked is False
    assert len(result.observations) == 3
    assert all(o.extracted for o in result.observations)
    assert all(o.citations for o in result.observations)


def test_the_upload_identifier_is_reported(target):
    result = validate(config_for(target()), timeout=5.0)
    assert result.upload.ok
    assert result.upload.identifier == "doc-1"


def test_skip_upload_says_what_went_unchecked(target):
    result = validate(config_for(target()), timeout=5.0, skip_upload=True)
    assert result.upload.attempted is False
    assert "unknown" in result.upload.skipped_because
    assert "upload_no_identifier" not in {d.code for d in result.diagnoses}


def test_the_retrieval_endpoint_is_exercised_when_configured(target):
    url = target()
    config = config_for(
        url, target={"endpoints": {
            "chat": f"{url}/chat",
            "upload": f"{url}/documents",
            "retrieval": {"url": f"{url}/retrieve", "method": "GET"},
        }}
    )
    result = validate(config, timeout=5.0)
    assert "1 chunks" in (result.retrieval or "")


# -------------------------------------------- one test per row of §7.1's table


def codes(result) -> set[str]:
    return {d.code for d in result.diagnoses}


def test_auth_rejection_is_named_not_scored(target):
    result = validate(config_for(target("auth")), timeout=5.0)
    assert "auth_rejected" in codes(result)
    assert result.blocked

    diagnosis = next(d for d in result.diagnoses if d.code == "auth_rejected")
    # The second column of §7.1's table is the reason the mode exists, so it is carried
    # in the diagnosis rather than left for the operator to infer.
    assert "empty answer" in diagnosis.mistaken_for


def test_a_transport_failure_is_not_also_reported_as_two_wrong_paths(target):
    """Found by reading the output, not by a test.

    A 401 produces three empty answers and no citations, and the first version added
    `citations_not_extracted` underneath the auth diagnosis — sending the operator to a
    config key that was almost certainly correct while the real cause sat above it. Same
    rule as the report itself: an absent measurement and a failed one must not print the
    same (F40).
    """
    result = validate(config_for(target("auth")), timeout=5.0)
    assert codes(result) == {"auth_rejected"}


def test_rate_limiting_is_named_rather_than_read_as_non_determinism(target):
    result = validate(config_for(target("rate_limit")), timeout=5.0)
    assert "rate_limited" in codes(result)
    diagnosis = next(d for d in result.diagnoses if d.code == "rate_limited")
    assert "8.3" in diagnosis.mistaken_for or "variance" in diagnosis.mistaken_for


def test_a_stream_that_never_terminates_is_named(target):
    config = config_for(
        target("sse_forever"),
        response_format={
            "answer_field": "delta",
            "citations_field": "sources",
            "stream": True,
            "stop_payload_match": "[DONE]",
        },
    )
    result = validate(config, timeout=1.0)
    assert "stream_never_terminated" in codes(result)
    assert all(o.ended_by == "deadline" for o in result.observations)


def test_a_stream_that_does_terminate_is_clean(target):
    """The other half: the deadline must not fire on a well-behaved stream."""
    config = config_for(
        target("sse_clean"),
        response_format={
            "answer_field": "delta",
            "citations_field": "sources",
            "stream": True,
            "stop_payload_match": "[DONE]",
        },
    )
    result = validate(config, timeout=5.0)
    assert "stream_never_terminated" not in codes(result)
    assert all(o.ended_by == "terminator" for o in result.observations)
    assert all("searches" in (o.answer or "") for o in result.observations)


def test_a_websocket_that_says_nothing_is_named_as_a_handshake_problem(target):
    """A connection that opens and stays silent — the §7.1 `init_message` row.

    Indistinguishable, from the transport's side, from a system that declined to
    answer. That is the whole reason it needs naming here rather than at scoring time.
    """
    websockets = pytest.importorskip("websockets")

    ready = threading.Event()
    port: list[int] = []

    async def silent(_connection):
        await asyncio.sleep(5)

    def serve():
        async def main():
            async with websockets.serve(silent, "127.0.0.1", 0) as server:
                port.append(server.sockets[0].getsockname()[1])
                ready.set()
                await asyncio.sleep(10)

        asyncio.run(main())

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(5), "the stub websocket server did not start"

    url = target()
    config = config_for(
        url,
        target={"endpoints": {
            "chat": f"{url}/chat",
            "upload": f"{url}/documents",
            "receive": {"url": f"ws://127.0.0.1:{port[0]}", "init_message": {"a": 1}},
        }},
    )
    result = validate(config, timeout=1.0)
    assert "handshake_failed" in codes(result)
    assert result.blocked


def test_a_refused_websocket_names_the_websocket_url_not_the_chat_one(target):
    """A connection that never opened is a problem with the address it tried to open."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead = probe.getsockname()[1]

    url = target()
    config = config_for(
        url,
        target={"endpoints": {
            "chat": f"{url}/chat",
            "upload": f"{url}/documents",
            "receive": {"url": f"ws://127.0.0.1:{dead}"},
        }},
    )
    result = validate(config, timeout=2.0)
    diagnosis = next(d for d in result.diagnoses if d.code == "unreachable")
    assert f"127.0.0.1:{dead}" in diagnosis.saw, (
        "the chat endpoint answered fine; naming it here would send the reader to the "
        "wrong line of their config"
    )
    assert "handshake_failed" not in codes(result), (
        "the connection never opened, so `init_message` is not the thing to change"
    )


def test_a_poll_that_never_yields_an_answer_is_not_called_a_stream(target):
    """`receive` over HTTP has no terminator to configure, so the stream remedy is wrong.

    The GET-poll shape of `endpoints.receive` is one §7.1's table does not name, and the
    first version reported it with the SSE diagnosis — pointing the reader at
    `stop_payload_match`, a key this configuration does not use.
    """
    url = target()
    config = config_for(
        url,
        response_format={"answer_field": "response.never_here"},
        target={"endpoints": {
            "chat": f"{url}/chat",
            "upload": f"{url}/documents",
            "receive": {"url": f"{url}/poll", "method": "GET"},
        }},
    )
    result = validate(config, timeout=2.0)
    assert "answer_never_arrived" in codes(result)
    assert "stream_never_terminated" not in codes(result)
    printed = render(result)
    assert "polls, the answer never arrived" in printed
    assert "ended by our deadline" not in printed


def test_a_retry_after_header_reaches_the_rate_limit_diagnosis(target):
    result = validate(config_for(target("rate_limit_retry")), timeout=5.0)
    diagnosis = next(d for d in result.diagnoses if d.code == "rate_limited")
    assert "wait 30s" in diagnosis.saw


def test_an_upload_with_no_identifier_is_named_and_does_not_stop_the_run(target):
    result = validate(config_for(target("upload_no_id")), timeout=5.0)
    assert "upload_no_identifier" in codes(result)
    diagnosis = next(d for d in result.diagnoses if d.code == "upload_no_identifier")
    assert diagnosis.blocking is False, (
        "a target that issues no document identifiers is a real loss of one Tier 1 "
        "check and a perfectly runnable engagement"
    )
    assert not result.blocked


def test_a_slow_target_projects_the_run_length(target):
    config = config_for(target("slow", delay=0.4))
    # 400 ms × 19 probes × 3 passes is nowhere near an hour, so the projection is
    # printed and no diagnosis fires. Asserted against a probe count large enough to
    # cross the line, which is what an engagement-sized battery would do.
    result = validate(config, timeout=5.0, passes=3, probe_count=4000)
    assert "run_too_long" in codes(result)
    assert result.projected_seconds > 3600
    assert next(d for d in result.diagnoses if d.code == "run_too_long").blocking is False


def test_a_fast_target_projects_without_a_diagnosis(target):
    result = validate(config_for(target()), timeout=5.0, passes=1)
    assert "run_too_long" not in codes(result)
    assert result.median_ms is not None
    assert result.projected_seconds < 3600


# ----------------------------------------- the leading cause of false positives


def test_a_wrong_answer_path_is_named_and_candidates_are_offered(target):
    result = validate(config_for(target("wrong_path")), timeout=5.0)
    assert "answer_not_extracted" in codes(result)
    assert result.blocked

    diagnosis = next(d for d in result.diagnoses if d.code == "answer_not_extracted")
    assert "result.message" in diagnosis.remedy, (
        "the longest string in the body is the answer, and the operator should not "
        "have to find it themselves"
    )


def test_a_wrong_citations_path_is_advisory_not_blocking(target):
    """A system that cites nothing is a finding; a path that reads nothing is not."""
    config = config_for(
        target(), response_format={"citations_field": "response.references"}
    )
    result = validate(config, timeout=5.0)
    assert "citations_not_extracted" in codes(result)
    assert not result.blocked


def test_an_unreachable_target_is_named_rather_than_raised():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    result = validate(config_for(f"http://127.0.0.1:{port}"), timeout=2.0)
    assert "unreachable" in codes(result)
    assert result.blocked


def test_a_server_error_is_named_rather_than_read_as_an_empty_answer(target):
    result = validate(config_for(target("server_error")), timeout=5.0)
    assert codes(result) == {"bad_status"}, (
        "a body that never arrived is not a path that failed to match one; the "
        "extraction diagnoses would bury the real cause under two false leads"
    )


def test_one_diagnosis_per_condition_not_one_per_probe(target):
    result = validate(config_for(target("auth")), timeout=5.0)
    assert len([d for d in result.diagnoses if d.code == "auth_rejected"]) == 1


# ------------------------------------------------------- the path suggestions


BODY = {
    "result": {
        "message": "A long answer that is clearly the prose in this response body.",
        "request_id": "abc-123",
    },
    "documents": [{"ref": "d1"}, {"ref": "d2"}],
    "tags": ["one", "two"],
}


def test_every_suggested_path_parses_and_finds_what_it_claims():
    """A suggestion that does not parse is worse than no suggestion."""
    from jsonpath_ng.ext import parse

    for candidate in answer_candidates(BODY) + citation_candidates(BODY):
        found = parse(candidate.path).find(BODY)
        assert found, f"{candidate.path} matched nothing in the body it came from"


def test_the_longest_string_is_offered_first():
    candidates = answer_candidates(BODY)
    assert candidates[0].path == "result.message"


def test_short_strings_are_not_offered_as_answers():
    paths = [c.path for c in answer_candidates(BODY)]
    assert "result.request_id" not in paths


def test_arrays_are_offered_in_document_order():
    paths = [c.path for c in citation_candidates(BODY)]
    assert paths[0] == "documents"


def test_a_key_that_is_not_an_identifier_is_quoted():
    from jsonpath_ng.ext import parse

    body = {"a-b": {"c": "A long answer sitting under an awkward key name."}}
    candidate = answer_candidates(body)[0]
    assert candidate.path == "['a-b'].c"
    assert parse(candidate.path).find(body)


def test_suggestions_are_stable_for_the_same_body():
    assert [c.path for c in answer_candidates(BODY)] == [
        c.path for c in answer_candidates(BODY)
    ]


# ---------------------------------------------------------------- the rendering


def test_the_raw_body_is_printed_before_our_reading_of_it(target):
    printed = render(validate(config_for(target()), timeout=5.0))
    assert printed.index("    raw:") < printed.index("    extracted:")


def test_candidates_are_labelled_as_guesses(target):
    printed = render(validate(config_for(target("wrong_path")), timeout=5.0))
    assert "guesses" in printed
    assert "not answers" in printed


def test_no_candidates_are_offered_when_the_config_works(target):
    printed = render(validate(config_for(target()), timeout=5.0))
    assert "Candidate paths" not in printed


def test_a_clean_run_says_what_it_did_not_establish(target):
    printed = render(validate(config_for(target()), timeout=5.0))
    assert "says nothing about the target" in printed


def test_the_render_names_the_exit_code_for_a_blocked_run(target):
    printed = render(validate(config_for(target("auth")), timeout=5.0))
    assert "Exit 2" in printed
    assert "not findings about the target" in printed


# ------------------------------------------------------------------ exit codes


def cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "legal_rag_audit.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd or str(REPO_ROOT),
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )


def write_config(tmp_path: Path, url: str, name="config.yaml") -> Path:
    path = tmp_path / name
    path.write_text(
        "target:\n"
        "  name: stub\n"
        "  endpoints:\n"
        f"    chat: {url}/chat\n"
        f"    upload: {url}/documents\n"
        "  response_format:\n"
        "    answer_field: response.text\n"
        "    citations_field: response.sources\n",
        encoding="utf-8",
    )
    return path


def test_a_clean_target_exits_zero(target, tmp_path):
    config = write_config(tmp_path, target())
    assert cli("validate", "-c", str(config)).returncode == 0


def test_a_setup_problem_exits_two_not_one(target, tmp_path):
    config = write_config(tmp_path, target("auth"))
    result = cli("validate", "-c", str(config))
    assert result.returncode == 2, (
        "exit 1 means 'ran, findings'. validate judges no answer, so it has no "
        "findings, and sharing the code would be the conflation the mode prevents"
    )


def test_a_missing_config_exits_two(tmp_path):
    result = cli("validate", "-c", str(tmp_path / "nope.yaml"))
    assert result.returncode == 2


def test_the_probe_file_sets_the_projection_count(target, tmp_path):
    """Counting lines in a file, rather than importing the battery to measure it."""
    probes = tmp_path / "probes.jsonl"
    probes.write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    config = write_config(tmp_path, target())
    result = cli("validate", "-c", str(config), "--probes", str(probes))
    assert result.returncode == 0
    assert "× 3 probes" in result.stdout
    assert str(probes) in result.stdout


# ------------------------------------------------- what is shared with generate


def test_validate_substitutes_the_same_variables_as_the_transport():
    """The templating table is copied, so a test has to hold the two together."""
    import inspect

    from legal_rag_audit.transport import client as transport
    from legal_rag_audit.validate import run as validate_run

    chat = inspect.getsource(transport.TargetClient.chat)
    ours = inspect.getsource(validate_run._variables)
    for token in ("QUERY", "UUID", 'replace("-", "_")'):
        assert token in chat and token in ours, (
            f"{token} is in one substitution table and not the other; a config using "
            f"it would validate and then behave differently under `generate`"
        )


def test_validate_uses_the_configured_paths_rather_than_its_own(target):
    """What is validated has to be the config `generate` will run with."""
    config = config_for(
        target("wrong_path"), response_format={"answer_field": "result.message"}
    )
    result = validate(config, timeout=5.0)
    assert all("Companies Act" in (o.answer or "") for o in result.observations)
    assert "answer_not_extracted" not in codes(result)
