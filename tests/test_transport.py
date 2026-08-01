"""The transport handles both endpoint spellings §6.1 allows.

`endpoints.chat` may be a bare URL string or a full object with headers and a body
template. `chat()` read `.headers` off it unconditionally, so every request failed with
an AttributeError when the string form was used — the form the README example uses.

Uploads took the same union and handled it, which is why the failure looked like a
target problem rather than ours: the corpus went up, and then every probe came back as
a transport error.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from legal_rag_audit.config import AuditConfig
from legal_rag_audit.transport import TargetClient


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        body = json.dumps(
            {"response": {"text": f"answered: {payload.get('query', '')}", "sources": ["d1"]}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def stub():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def config_for(url: str, *, object_form: bool) -> AuditConfig:
    chat = (
        {"url": f"{url}/chat", "method": "POST", "headers": {"X-Test": "1"}}
        if object_form
        else f"{url}/chat"
    )
    return AuditConfig(
        **{
            "target": {
                "name": "stub",
                "endpoints": {"chat": chat, "upload": f"{url}/documents"},
                "auth": {"type": "none"},
                "response_format": {
                    "answer_field": "response.text",
                    "citations_field": "response.sources",
                },
            },
            "corpus": {"use_bundled": True},
        }
    )


async def _chat_once(url, object_form):
    client = TargetClient(config_for(url, object_form=object_form).target)
    try:
        return await client.chat("what is the cap?")
    finally:
        await client.close()


@pytest.mark.parametrize("object_form", [False, True], ids=["string-url", "object"])
def test_chat_works_for_both_endpoint_spellings(stub, object_form):
    import asyncio

    result = asyncio.run(_chat_once(stub, object_form))
    assert result["answer"] == "answered: what is the cap?"
    assert result["citations"] == ["d1"]


def test_a_string_endpoint_has_no_headers_to_read():
    """The precise shape of the bug, without a server.

    A regression here is silent at import time and only appears as every probe failing,
    so it is worth asserting directly rather than only through a round trip.
    """
    config = config_for("http://example.invalid", object_form=False)
    assert isinstance(config.target.endpoints.chat, str)
    assert getattr(config.target.endpoints.chat, "headers", None) is None
