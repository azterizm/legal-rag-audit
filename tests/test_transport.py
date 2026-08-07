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
            "corpus": {"mode": "existing", "path": "/tmp"},
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


# --------------------------------------------------------- selecting a frame by type
#
# A streaming target's frames are typed, and the second live run of this tool is the
# argument for why the transport has to be able to see that. Its stream carried the
# model's reasoning, its tool arguments and its answer under the same key. The obvious
# JSONPath collected all three; the path chosen instead — the final message's second
# content block, after the thinking block — was verified byte-exact against a capture
# and then matched nothing on the one probe where the model returned no thinking block.
# `jsonpath_ng` filters do not apply to a dict root, so the frame type was not something
# a path could ask about. Now it is.

_FRAMES = [
    {"type": "thinking_delta", "content": "the user is asking about "},
    {"type": "thinking_delta", "content": "a statutory limit, let me search"},
    {"type": "toolcall_delta", "content": '{"query": "section 227"}'},
    {"type": "text_delta", "content": "The limit was "},
    {"type": "text_delta", "content": "£464 per week."},
    {"type": "text_end", "content": "The limit was £464 per week."},
    {"type": "done", "content": "The limit was £464 per week."},
]

ANSWER = "The limit was £464 per week."


class _StreamHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server's interface
        self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in _FRAMES:
            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
        self.wfile.flush()

    def log_message(self, *_args):
        pass


@pytest.fixture
def sse():
    server = HTTPServer(("127.0.0.1", 0), _StreamHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _stream_config(url: str, **response_format) -> AuditConfig:
    return AuditConfig(
        **{
            "target": {
                "name": "stub",
                "endpoints": {"chat": {"url": f"{url}/chat", "method": "POST"}},
                "auth": {"type": "none"},
                "response_format": {
                    "answer_field": "$.content",
                    "citations_field": "$.citations",
                    "stream": True,
                    **response_format,
                },
            },
            "corpus": {"mode": "existing", "path": "/tmp"},
        }
    )


def _stream_once(url, **response_format):
    import asyncio

    async def go():
        client = TargetClient(_stream_config(url, **response_format).target)
        try:
            return await client.chat("what was the limit?")
        finally:
            await client.close()

    return asyncio.run(go())


def test_without_a_selector_every_frame_is_read_as_answer(sse):
    """The behaviour that was there before, and the reason it is not enough.

    Every frame carries `content`, so the reasoning and the tool arguments land in the
    answer alongside it. Asserted rather than assumed, because this is what a config
    that omits the selector still gets.
    """
    answer = _stream_once(sse)["answer"]
    assert "the user is asking about" in answer
    assert '{"query": "section 227"}' in answer
    assert answer != ANSWER


def test_a_frame_selector_takes_the_answer_and_nothing_else(sse):
    result = _stream_once(
        sse, answer_frame_field="$.type", answer_frame_value="text_end"
    )
    assert result["answer"] == ANSWER


def test_the_selector_can_name_the_delta_frames_instead(sse):
    """Selecting the streamed pieces is the other legitimate reading of the same stream,
    and it must reassemble to the same answer or one of the two is lying."""
    result = _stream_once(
        sse, answer_frame_field="$.type", answer_frame_value="text_delta"
    )
    assert result["answer"] == ANSWER


def test_a_selector_matching_no_frame_yields_no_answer_rather_than_the_wrong_one(sse):
    """The failure has to stay loud. `generate` records an empty answer as a transport
    failure, so a mis-named frame type costs a re-run — never a page of findings about a
    target that did answer."""
    result = _stream_once(
        sse, answer_frame_field="$.type", answer_frame_value="no_such_frame"
    )
    assert result["answer"] == ""


@pytest.mark.parametrize(
    "half", [{"answer_frame_field": "$.type"}, {"answer_frame_value": "text_end"}]
)
def test_half_a_selector_is_refused_at_load(half):
    """One half alone matches every frame or none of them, and both are wrong quietly."""
    with pytest.raises(Exception, match="frame selector"):
        _stream_config("http://example.invalid", **half)
