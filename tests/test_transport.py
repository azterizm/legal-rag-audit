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


# --------------------------------------------------------------------------------
# Asynchronous targets: submit returns a ticket, the answer is polled for.
#
# The third live target answers this way, and none of it could be configured before.
# The poll URL contains an identifier that does not exist until the submit returns, and
# the polled record exists from the moment of submit with an empty answer field — so
# both "where is the ticket" and "when is it finished" have to be said explicitly. The
# tests below are the three ways that goes wrong.

ASYNC_ANSWER = "As at 1 June 2014 the limit on a week's pay was £464."


class _AsyncHandler(BaseHTTPRequestHandler):
    #: How many polls return `generating` before one returns `saved`.
    generating_polls = 2
    polls = 0

    def do_POST(self):  # noqa: N802 - http.server's interface
        self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
        type(self).polls = 0
        self._json(
            201,
            {
                "conversation": {"id": "conv-1"},
                "userMessage": {"id": "user-1"},
                # The answer's handle, and the only thing that identifies it.
                "aiMessage": {"id": "msg-42", "status": "generating", "text": ""},
            },
        )

    def do_GET(self):  # noqa: N802 - http.server's interface
        if not self.path.endswith("/msg-42"):
            self._json(404, {"error": "no such message"})
            return
        type(self).polls += 1
        if type(self).polls <= type(self).generating_polls:
            # The shape that breaks the old rule: the record is already there, and the
            # answer field is already present and empty.
            self._json(200, {"id": "msg-42", "status": "generating", "text": "",
                             "legalSources": []})
        else:
            self._json(200, {"id": "msg-42", "status": "saved", "text": ASYNC_ANSWER,
                             "legalSources": [{"title": "ERA 1996 s.227"}]})

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def async_target():
    _AsyncHandler.generating_polls = 2
    server = HTTPServer(("127.0.0.1", 0), _AsyncHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _async_config(url: str, **response_format) -> AuditConfig:
    return AuditConfig(
        **{
            "target": {
                "name": "stub",
                "endpoints": {
                    "chat": {"url": f"{url}/analyzer", "method": "POST",
                             "body": {"message": {"text": "{{QUERY}}"}}},
                    "receive": {"url": url + "/chat_message/{{HANDLE}}", "method": "GET"},
                },
                "auth": {"type": "none"},
                "response_format": {
                    "answer_field": "$.text",
                    "citations_field": "$.legalSources",
                    "poll_interval_seconds": 0.01,
                    "poll_timeout_seconds": 5.0,
                    **response_format,
                },
            },
            "corpus": {"mode": "existing", "path": "/tmp"},
        }
    )


def _async_once(url, **response_format):
    import asyncio

    async def go():
        client = TargetClient(_async_config(url, **response_format).target)
        try:
            return await client.chat("what was the limit on 1 June 2014?")
        finally:
            await client.close()

    return asyncio.run(go())


def test_the_handle_comes_from_the_submit_response(async_target):
    """The poll URL is not knowable before the submit, which is the whole point.

    `{{HANDLE}}` resolves to `aiMessage.id`; the stub 404s any other path, so an
    unresolved template fails the test rather than passing by luck.
    """
    result = _async_once(
        async_target,
        handle_field="$.aiMessage.id",
        ready_field="$.status",
        ready_value="saved",
    )
    assert result["answer"] == ASYNC_ANSWER
    assert result["citations"] == [{"title": "ERA 1996 s.227"}]


def test_polling_waits_for_ready_rather_than_for_the_answer_field(async_target):
    """The defect this was written for.

    The record carries `text: ""` from the moment of submit. Stopping when the answer
    path matches — the rule every earlier config used — returns that empty string on the
    first poll, and an empty answer is indistinguishable from a system that declined to
    answer. Two polls must go by before the answer appears.
    """
    _AsyncHandler.generating_polls = 3
    result = _async_once(
        async_target,
        handle_field="$.aiMessage.id",
        ready_field="$.status",
        ready_value="saved",
    )
    assert result["answer"] == ASYNC_ANSWER
    assert _AsyncHandler.polls == 4


def test_without_ready_the_empty_answer_comes_straight_back(async_target):
    """Left in deliberately, as the record of why `ready_field` is not optional here.

    This is the pre-existing behaviour and it is still correct for targets that create
    the answer field only once they have an answer. Against this shape it is wrong, and
    silently: a well-formed empty result, on the first poll, for every probe.
    """
    result = _async_once(async_target, handle_field="$.aiMessage.id")
    assert result["answer"] == ""
    assert _AsyncHandler.polls == 1


def test_an_answer_that_never_arrives_raises_rather_than_returning_empty(async_target):
    """F40, one layer below where it is usually enforced.

    Returning `""` on an exhausted budget would have `generate` write a record that
    reads exactly like a target with nothing to say. A raise becomes a transport error,
    and a transport error is not a result about anyone.
    """
    _AsyncHandler.generating_polls = 10_000
    with pytest.raises(TimeoutError, match="nothing about this probe was measured"):
        _async_once(
            async_target,
            handle_field="$.aiMessage.id",
            ready_field="$.status",
            ready_value="saved",
            poll_timeout_seconds=0.2,
        )


def test_a_handle_path_that_matches_nothing_is_refused_at_run(async_target):
    """A mistyped path would otherwise poll a URL with `{{HANDLE}}` still in it."""
    with pytest.raises(RuntimeError, match="matched nothing"):
        _async_once(
            async_target,
            handle_field="$.aiMessage.identifier",
            ready_field="$.status",
            ready_value="saved",
        )


@pytest.mark.parametrize(
    "half", [{"ready_field": "$.status"}, {"ready_value": "saved"}]
)
def test_half_a_readiness_test_is_refused_at_load(half):
    with pytest.raises(Exception, match="readiness test"):
        _async_config("http://example.invalid", **half)
