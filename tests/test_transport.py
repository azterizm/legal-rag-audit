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


class _EchoHandler(BaseHTTPRequestHandler):
    """Answers with the request body, so a test can assert what went on the wire."""

    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) or b"{}"
        payload = json.loads(raw)
        body = json.dumps({"response": {"text": json.dumps(payload), "sources": []}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def echo():
    server = HTTPServer(("127.0.0.1", 0), _EchoHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _attaching_config(url: str) -> AuditConfig:
    return AuditConfig(
        **{
            "target": {
                "name": "stub",
                "endpoints": {
                    "chat": {
                        "url": f"{url}/chat",
                        "method": "POST",
                        "body": {
                            "messages": [
                                {
                                    "role": "user",
                                    "content": "{{QUERY}}",
                                    "files": "{{ATTACHMENTS}}",
                                }
                            ]
                        },
                    },
                    "upload": f"{url}/documents",
                },
                "auth": {"type": "none"},
                "response_format": {
                    "answer_field": "response.text",
                    "citations_field": "response.sources",
                },
            },
            "corpus": {"mode": "existing", "path": "/tmp"},
        }
    )


def _sent(url, **kwargs) -> dict:
    import asyncio

    client = TargetClient(_attaching_config(url).target)

    async def go():
        try:
            return await client.chat('what is the "cap"?', **kwargs)
        finally:
            await client.close()

    return json.loads(asyncio.run(go())["answer"])


def test_attachments_go_out_as_a_list_not_a_repr(echo):
    """Documents are uploaded once; the chat turn names them by the id upload issued.

    The substitution has to hand over the list itself. Interpolating it into a string
    would send `[{'filename': ...}]` — Python repr, single quotes — to a JSON API, which
    is a transport error scored against the target.
    """
    files = [{"filename": "a.txt", "document_id": "d-1"}]
    sent = _sent(echo, attachments=files)

    assert sent["messages"][0]["files"] == files


def test_a_probe_containing_quotes_survives_a_mapping_body(echo):
    """Injection payloads are full of quotes. A JSON-string body template would break."""
    sent = _sent(echo, attachments=[])

    assert sent["messages"][0]["content"] == 'what is the "cap"?'


def test_no_attachments_substitutes_an_empty_list(echo):
    """An existing-corpus run must not leave `{{ATTACHMENTS}}` on the wire."""
    sent = _sent(echo)

    assert sent["messages"][0]["files"] == []


def _auth_config(**auth) -> AuditConfig:
    return AuditConfig(
        **{
            "target": {
                "name": "stub",
                "endpoints": {"chat": "http://example.invalid/chat"},
                "auth": auth,
                "response_format": {
                    "answer_field": "response.text",
                    "citations_field": "response.sources",
                },
            },
            "corpus": {"mode": "existing", "path": "/tmp"},
        }
    )


def test_a_credential_in_the_file_is_sent():
    """For a self-contained run config that is deleted after the run."""
    client = TargetClient(_auth_config(type="bearer", token="live-token").target)

    assert client.headers["Authorization"] == "Bearer live-token"


def test_naming_both_a_token_and_an_env_var_is_refused():
    """Which one is live cannot be read off the file, and a stale one sends 401s that
    would be recorded as answers the target gave."""
    with pytest.raises(Exception) as e:
        _auth_config(type="bearer", token="a", token_env="B")

    assert "Keep one" in str(e.value)


def test_a_blank_in_file_token_is_refused_at_load():
    """A credential lost to a bad copy-paste is caught here or not at all — otherwise
    every rejection of an empty Bearer header is recorded as an answer."""
    with pytest.raises(Exception) as e:
        _auth_config(type="bearer", token="   ")

    assert "blank string" in str(e.value)


def test_a_pasted_token_is_stripped():
    """YAML block scalars and clipboards both bring newlines; an Authorization header
    carrying one is a 400 on some servers and a silent mismatch on others."""
    client = TargetClient(_auth_config(type="bearer", token="live-token\n").target)

    assert client.headers["Authorization"] == "Bearer live-token"


class _StagedHandler(BaseHTTPRequestHandler):
    """A target that generates nothing until it is driven, one stage per request.

    Modelled on Justice Pappers: create returns a uuid, the first stage answers JSON
    (retrieved articles), the second an event stream of case law, the third the answer —
    all three frame shapes identical, distinguished only by the SSE event name.
    """

    stages = 0

    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)

        if self.path == "/create":
            body = json.dumps({"uuid": "u-1"}).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        assert self.path == "/question/u-1/etape", self.path
        type(self).stages += 1
        stage = type(self).stages

        if stage == 1:
            body = json.dumps({"articles": [{"id": "LEGIARTI1"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if stage == 2:
            frames = [("decision", "Cass. civ. 1re"), ("complete", "")]
        else:
            frames = [
                ("message", "Les contrats "),
                ("message", "obligent."),
                ("enhanced", "Si je devais challenger cette reponse"),
                ("complete", ""),
            ]
        for name, content in frames:
            self.wfile.write(
                f"event: {name}\ndata: {json.dumps({'content': content})}\n\n".encode()
            )
            self.wfile.flush()

    def log_message(self, *_args):
        pass


@pytest.fixture
def staged():
    _StagedHandler.stages = 0
    server = HTTPServer(("127.0.0.1", 0), _StagedHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _driven(url: str) -> dict:
    import asyncio

    config = AuditConfig(
        **{
            "target": {
                "name": "staged",
                "endpoints": {
                    "chat": {
                        "url": f"{url}/create",
                        "method": "POST",
                        "body": {"question": "{{QUERY}}"},
                    },
                    "receive": {
                        "url": f"{url}/question/{{{{HANDLE}}}}/etape",
                        "method": "POST",
                        "body": {"mode": "long"},
                    },
                },
                "auth": {"type": "none"},
                "response_format": {
                    "stream": True,
                    "handle_field": "$.uuid",
                    "answer_field": "$.content",
                    "citations_field": "$.articles",
                    "answer_event": "message",
                    "stop_event": "complete",
                    "poll_interval_seconds": 0.01,
                    "poll_timeout_seconds": 10.0,
                },
            },
            "corpus": {"mode": "existing", "path": "/tmp"},
        }
    )
    client = TargetClient(config.target)

    async def go():
        try:
            return await client.chat("quelle est la regle?")
        finally:
            await client.close()

    return asyncio.run(go())


def test_a_target_that_must_be_driven_is_driven_until_it_answers(staged):
    """Stages that carry no answer are steps on the way, not failures — the loop keeps
    going rather than recording an empty answer from the first one."""
    result = _driven(staged)

    assert result["answer"] == "Les contrats obligent."
    assert _StagedHandler.stages == 3


def test_the_self_critique_event_is_not_part_of_the_answer(staged):
    """`enhanced` frames carry the model's criticism of the answer it just gave, in the
    same `{"content": …}` shape as the answer. Scoring them as answer text would report a
    system's self-doubt as something it told the user."""
    result = _driven(staged)

    assert "challenger" not in result["answer"]


def test_citations_survive_the_stage_that_carried_them(staged):
    """Retrieval and generation are different stages; the articles arrive on the first
    and the answer on the third, and a run that returned only the last stage would score
    a citing system as one that cites nothing."""
    result = _driven(staged)

    assert result["citations"] == [{"id": "LEGIARTI1"}]


# --- Multipart uploads that carry more than the file -------------------------------


class _MultipartHandler(BaseHTTPRequestHandler):
    """Records the raw multipart body of an upload so a test can read the parts."""

    last_body = b""
    last_type = ""

    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length", 0))
        _MultipartHandler.last_body = self.rfile.read(length)
        _MultipartHandler.last_type = self.headers.get("Content-Type", "")
        body = json.dumps({"request_id": "job-1"}).encode()
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def multipart():
    _MultipartHandler.last_body = b""
    server = HTTPServer(("127.0.0.1", 0), _MultipartHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _upload_config(url: str, body) -> AuditConfig:
    upload = {"url": f"{url}/ingest", "method": "POST", "file_field": "files"}
    if body is not None:
        upload["body"] = body
    return AuditConfig(
        **{
            "target": {
                "name": "stub",
                "endpoints": {"chat": f"{url}/chat", "upload": upload},
                "auth": {"type": "none"},
            },
            "corpus": {"mode": "existing", "path": "/tmp"},
        }
    )


def _uploaded(url, body) -> bytes:
    import asyncio

    client = TargetClient(_upload_config(url, body).target)

    async def go():
        try:
            return await client.upload_document("plant.md", "seeded fact")
        finally:
            await client.close()

    asyncio.run(go())
    return _MultipartHandler.last_body


def test_form_fields_beside_the_file_reach_the_target(multipart):
    """An ingest route that needs an owner and an OCR mode alongside the file.

    Gaius Lex is the case: `owner`, `path` and `ocr_mode` travel in the same multipart
    body as the document. Before this the body was parsed and then discarded, so the
    upload went out missing the fields the target requires — and a rejected upload is a
    corpus the target never held, scored as answers about documents it does not have.
    """
    sent = _uploaded(
        multipart, {"owner": "operator@example.test", "path": "", "ocr_mode": "auto"}
    )

    assert b'name="files"' in sent
    assert b"seeded fact" in sent
    assert b'name="owner"' in sent and b"operator@example.test" in sent
    assert b'name="ocr_mode"' in sent and b"auto" in sent


def test_without_a_declared_body_the_file_still_travels_alone(multipart):
    """The default payload is the file itself, not fields to send beside it.

    With no `body:` the prepared payload is `{filename, content}` — sending those as
    form fields would put the whole document in the multipart body twice and hand the
    target a field it never asked for.
    """
    sent = _uploaded(multipart, None)

    assert b'name="files"' in sent
    assert b'name="content"' not in sent
    assert b'name="filename"' not in sent


# --- Targets that take the question on the socket ----------------------------------


def _socket_config(ws_url: str) -> AuditConfig:
    return AuditConfig(
        **{
            "target": {
                "name": "stub",
                "endpoints": {
                    "chat": {
                        "url": ws_url,
                        "body": {"message": "{{QUERY}}", "documents": []},
                    },
                    "receive": {"url": ws_url},
                },
                "auth": {"type": "none"},
                "response_format": {
                    "answer_field": "$.answer",
                    "citations_field": "$.markers",
                    "answer_frame_field": "$.message",
                    "answer_frame_value": "done",
                },
            },
            "corpus": {"mode": "existing", "path": "/tmp"},
        }
    )


@pytest.fixture
def socket_target():
    """A websocket that takes the question on the socket and streams cumulative answers.

    Gaius Lex's shape: every frame carries the answer *so far*, not the delta, and the
    last one says `done`.
    """
    import asyncio

    import websockets

    received = []
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    port = {}

    async def handler(connection):
        received.append(json.loads(await connection.recv()))
        for partial in ["Zgodnie z", "Zgodnie z art. 415", "Zgodnie z art. 415 KC."]:
            await connection.send(
                json.dumps({"message": "generating", "answer": partial, "markers": None})
            )
        await connection.send(
            json.dumps(
                {
                    "message": "done",
                    "answer": "Zgodnie z art. 415 KC.",
                    "markers": [{"id": "S1"}],
                }
            )
        )

    async def serve():
        server = await websockets.serve(handler, "127.0.0.1", 0)
        port["value"] = server.sockets[0].getsockname()[1]
        ready.set()
        await asyncio.Future()

    def run():
        loop.run_until_complete(serve())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    ready.wait(timeout=10)
    try:
        yield f"ws://127.0.0.1:{port['value']}/ws", received
    finally:
        loop.call_soon_threadsafe(loop.stop)


def _asked(ws_url) -> dict:
    import asyncio

    client = TargetClient(_socket_config(ws_url).target)

    async def go():
        try:
            return await client.chat("czym jest odpowiedzialność deliktowa?")
        finally:
            await client.close()

    return asyncio.run(go())


def test_the_question_goes_out_on_the_socket_when_there_is_no_chat_route(socket_target):
    """A target with no HTTP send route sends on the same connection it receives on.

    Without this the config would have to name some unrelated endpoint as `chat` purely
    to satisfy a request the target never receives — a file describing a run that does
    not happen, which is what §6.1 refuses.
    """
    ws_url, received = socket_target
    result = _asked(ws_url)

    assert received[0]["message"] == "czym jest odpowiedzialność deliktowa?"
    assert result["answer"] == "Zgodnie z art. 415 KC."


def test_a_cumulative_stream_is_not_concatenated_into_itself(socket_target):
    """Frames carrying the whole answer each time must not be summed.

    Read as deltas, four frames of a growing answer produce the answer four times over,
    and an evaluator scores a repetition the target never emitted.
    """
    ws_url, _ = socket_target
    result = _asked(ws_url)

    assert result["answer"].count("Zgodnie z") == 1
    assert result["citations"] == [{"id": "S1"}]
