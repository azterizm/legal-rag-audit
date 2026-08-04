"""The reference target as an HTTP service (V2_FULL_PLAN.md §14.1).

Three endpoints, which is the whole contract `generate` speaks:

    POST /upload     store a document, issue an identifier
    POST /chat       answer a question, with the sources it used
    POST /retrieval  the chunks behind the last answer

It runs over `http.server` rather than a framework because a reference target that
needed a web stack installed would be one more thing between a reader and the claim it
supports. It is a test double and it is meant to be readable in one sitting.

**Why this is worth running at all, rather than writing response files by hand.** A
fixture proves the scorer reads what we wrote. This proves the whole path: the corpus is
planted to disk, uploaded over HTTP, answered from what arrived, captured through the
transport client's JSONPaths, written to `responses.jsonl`, and scored against a key
sealed before any of it happened. Every seam between those is a place a real engagement
breaks, and none of them is exercised by a fixture.

The server holds no ground truth. It is constructed with the probe file and the profile,
and everything else it knows arrived through `/upload`.
"""

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

from legal_rag_audit.interchange.probe import Probe

from .oracle import Oracle, Reply
from .pathologies import Profile

UPLOAD_PATH = "/upload"
CHAT_PATH = "/chat"
RETRIEVAL_PATH = "/retrieval"


@dataclass
class Target:
    """Everything the reference target knows, and a lock over it.

    `ThreadingHTTPServer` answers each request on its own thread, so the pass counter
    and the index are shared state. A miscounted pass would make the `nondeterministic`
    profile fire on the wrong request, which is exactly the kind of flake that would
    make the gate untrustworthy.
    """

    profile: Profile
    oracle: Oracle
    lock: threading.Lock = field(default_factory=threading.Lock)
    #: probe_id -> how many times it has been asked. This is the pass index: nothing in
    #: the request says which pass it is, and a real target would have to count too.
    asked: dict[str, int] = field(default_factory=dict)
    #: Documents accepted at upload, in arrival order.
    uploaded: list[str] = field(default_factory=list)
    #: Queries the target did not recognise. Should always be empty; a non-empty list
    #: means the mock and the battery have moved apart, and the gate says so directly
    #: rather than letting it surface as a transport error scored as NOT_CAPTURED.
    unknown: list[str] = field(default_factory=list)
    #: The last reply produced for each probe, so `/retrieval` returns the chunks that
    #: belong to the answer rather than recomputing them.
    last: dict[str, Reply] = field(default_factory=dict)

    def upload(self, filename: str, content: str) -> str:
        with self.lock:
            self.oracle.ingest(filename, content)
            self.uploaded.append(filename)
        # The identifier is the filename. A target free to invent its own is the
        # general case; using the name we were given keeps the manifest legible and
        # keeps `fabricate_citations` the only source of an unresolvable identifier.
        return filename

    def answer(self, query: str) -> Optional[Reply]:
        with self.lock:
            probe_id = self.oracle.resolve(query)
            if probe_id is None:
                self.unknown.append(query)
                return None
            self.asked[probe_id] = self.asked.get(probe_id, 0) + 1
            pass_index = self.asked[probe_id]
            reply = self.profile.reply(
                self.oracle.reply(probe_id), self.oracle, pass_index
            )
            self.last[probe_id] = reply
        return reply

    def chunks(self, query: str) -> Optional[Reply]:
        """The retrieval behind the answer just given. Never advances the pass count."""
        with self.lock:
            probe_id = self.oracle.resolve(query)
            if probe_id is None:
                self.unknown.append(query)
                return None
            return self.last.get(probe_id)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_POST(self):  # noqa: N802 - http.server's interface
        path = urlparse(self.path).path
        target: Target = self.server.target
        payload = self._body()

        if path == UPLOAD_PATH:
            identifier = target.upload(payload.get("filename", ""), payload.get("content", ""))
            return self._send(200, {"id": identifier, "status": "stored"})

        query = payload.get("query", "")

        if path == CHAT_PATH:
            reply = target.answer(query)
            if reply is None:
                return self._send(400, {"error": "unrecognised query"})
            time.sleep(reply.delay_ms / 1000.0)
            return self._send(
                200,
                # Nothing but the answer and its sources. Chunks travel over
                # `/retrieval`, so nothing here carries a planted entity in a field
                # that is not the answer — a system that leaked one into a debug key
                # would be `entity_masking`'s metadata finding, and this profile set
                # does not claim to exercise it.
                {"response": {"text": reply.answer, "sources": reply.cited()}},
            )

        if path == RETRIEVAL_PATH:
            reply = target.chunks(query)
            if reply is None:
                return self._send(400, {"error": "unrecognised query"})
            return self._send(
                200,
                {
                    "data": [
                        {"content": chunk.text, "doc_id": chunk.doc_id}
                        for chunk in reply.chunks
                    ]
                },
            )

        return self._send(404, {"error": f"no endpoint at {path}"})


@dataclass
class Running:
    """A started reference target: where it is, and what it saw."""

    url: str
    target: Target

    @property
    def unknown_queries(self) -> list[str]:
        return list(self.target.unknown)

    @property
    def uploaded(self) -> list[str]:
        return list(self.target.uploaded)

    def endpoints(self) -> dict[str, str]:
        return {
            "chat": f"{self.url}{CHAT_PATH}",
            "upload": f"{self.url}{UPLOAD_PATH}",
            "retrieval": f"{self.url}{RETRIEVAL_PATH}",
        }


@contextmanager
def serve(profile: Profile, probes: list[Probe]) -> Iterator[Running]:
    """Run the reference target on a free port for the duration of the block."""
    target = Target(profile=profile, oracle=Oracle(probes))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.target = target
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Running(url=f"http://127.0.0.1:{server.server_address[1]}", target=target)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
