"""Standalone HTTP server running the mock reference target.

Usage:
    python scripts/serve_mock.py [--port 8000] [--profile clean|divergence|nondeterministic|answer_current_law] [--battery existing|planted]

Default is port 8000, profile 'divergence', battery 'existing'.
"""

import argparse
import json
import logging
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Add repo root and tests to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from legal_rag_audit.external import build_external_probes
from legal_rag_audit.plants import plant
from legal_rag_audit.probes import build_probes
from mock_target import BY_NAME as PROFILES, Oracle, Target, Profile, Reply

NEUTRAL_RESPONSES = {
    "What is this system for?": (
        "This system provides search and analysis across UK statutes and legal documents.",
        ["https://www.legislation.gov.uk/ukpga/1996/18"],
    ),
    "In two or three sentences, describe the kinds of documents you can search.": (
        "This system indexes primary UK legislation including the Employment Rights Act 1996 "
        "and the Companies Act 2006. It supports point-in-time statutory analysis across different enactments.",
        ["https://www.legislation.gov.uk/ukpga/1996/18", "https://www.legislation.gov.uk/ukpga/2006/46"],
    ),
    "Name up to three documents you can see, with their titles.": (
        "1. Employment Rights Act 1996 (c. 18)\n"
        "2. Companies Act 2006 (c. 46)\n"
        "3. SI 2011/3006 Employment Rights (Increase of Limits) Order 2011",
        ["https://www.legislation.gov.uk/ukpga/1996/18", "https://www.legislation.gov.uk/ukpga/2006/46"],
    ),
}


def _existing_divergence(reply: Reply, o: Oracle, pass_index: int) -> Reply:
    """Jimini-style value drift on probe pit-era-124-1 between pass 1 and passes 2/3."""
    if reply.probe_id == "pit-era-124-1":
        if pass_index > 1:
            reply.answer = (
                "Under section 124 of the Employment Rights Act 1996: "
                "Limit of compensatory award. 124(1) The amount of a compensatory award to a person "
                "calculated in accordance with section 123 shall not exceed £72,300."
            )
    return reply


class MockServerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        logging.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
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

    def do_POST(self):
        path = urlparse(self.path).path
        target: Target = self.server.target
        payload = self._body()

        if path in ("/upload", "/documents"):
            identifier = target.upload(payload.get("filename", ""), payload.get("content", ""))
            return self._send(200, {"id": identifier, "status": "stored"})

        query = payload.get("query", "").strip()

        if path in ("/chat", "/v1/query", "/query"):
            # Check neutral validate probes first
            if query in NEUTRAL_RESPONSES:
                text, sources = NEUTRAL_RESPONSES[query]
                return self._send(200, {"response": {"text": text, "sources": sources}})

            reply = target.answer(query)
            if reply is None:
                return self._send(200, {
                    "response": {
                        "text": f"Statutory query resolved: {query}",
                        "sources": ["https://www.legislation.gov.uk/"]
                    }
                })
            time.sleep(reply.delay_ms / 1000.0)
            return self._send(200, {"response": {"text": reply.answer, "sources": reply.cited()}})

        if path in ("/retrieval", "/v1/retrieval"):
            reply = target.chunks(query)
            if reply is None:
                return self._send(200, {"data": []})
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


def main():
    parser = argparse.ArgumentParser(description="Run the mock target server for legal-rag-audit.")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument(
        "--profile",
        default="divergence",
        help="Target behavior profile (default: divergence [Jimini-style value drift on pit-era-124-1], or clean, answer_current_law, nondeterministic)",
    )
    parser.add_argument(
        "--battery",
        default="existing",
        choices=["existing", "planted"],
        help="Battery mode (default: existing)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.profile == "divergence" or (args.profile == "nondeterministic" and args.battery == "existing"):
        profile = Profile(
            name="divergence",
            behaviour="Varies statutory cap on pit-era-124-1 between pass 1 (£68,400) and passes 2/3 (£72,300)",
            detects=("response_divergence",),
            probes=("pit-era-124-1",),
            apply=_existing_divergence,
            battery="existing",
            passes=3,
        )
    elif args.profile in PROFILES:
        profile = PROFILES[args.profile]
    else:
        profile = PROFILES["clean"]

    if args.battery == "existing":
        probes = build_external_probes(passes=profile.passes)
    else:
        corpus = plant("legal-rag-audit/reference-target/v2")
        probes = build_probes(passes=profile.passes, corpus=corpus)

    oracle = Oracle(probes)
    target = Target(profile=profile, oracle=oracle)

    server = ThreadingHTTPServer((args.host, args.port), MockServerHandler)
    server.target = target
    server.daemon_threads = True

    logging.info(
        "Mock Target running on http://%s:%d (profile=%s, battery=%s)",
        args.host,
        args.port,
        profile.name,
        args.battery,
    )
    logging.info("Endpoints: POST /chat, POST /v1/query, POST /upload, POST /retrieval")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down mock target...")
        server.server_close()


if __name__ == "__main__":
    main()
