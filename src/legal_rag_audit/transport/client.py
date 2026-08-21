import os
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
from jsonpath_ng.ext import parse

from ..config import TargetConfig

logger = logging.getLogger(__name__)


class AuthTokenMissing(Exception):
    """The configured credential is not in the environment. A setup problem (NF9)."""


class TargetClient:
    def __init__(self, target_config: TargetConfig):
        self.config = target_config
        self.headers = self._build_auth_headers()
        self.client = httpx.AsyncClient(timeout=60.0, headers=self.headers)
        
        self.answer_parser = parse(self.config.response_format.answer_field)
        self.citations_parser = parse(self.config.response_format.citations_field)
        self.stop_parser = parse(self.config.response_format.stop_field) if getattr(self.config.response_format, 'stop_field', None) else None
        # Which frames of a stream carry the answer. None means every frame, which is the
        # behaviour every config had before this existed.
        frame_field = getattr(self.config.response_format, 'answer_frame_field', None)
        self.answer_frame_parser = parse(frame_field) if frame_field else None
        # Asynchronous targets: where the ticket is in the submit response, and how a
        # polled body says it has finished. Both None keeps the older behaviour, which
        # was to poll until the answer path matched anything at all.
        handle_field = getattr(self.config.response_format, 'handle_field', None)
        self.handle_parser = parse(handle_field) if handle_field else None
        ready_field = getattr(self.config.response_format, 'ready_field', None)
        self.ready_parser = parse(ready_field) if ready_field else None

    def _build_auth_headers(self) -> Dict[str, str]:
        headers = {}
        auth = self.config.auth
        if auth.type != "none" and (auth.token_env or auth.token):
            # In-file first only when the env var is absent; the two cannot both be set
            # (AuthConfig refuses it), so there is no precedence to remember.
            token = auth.token or (
                os.environ.get(auth.token_env) if auth.token_env else None
            )
            if not token:
                # NF9. This used to warn and substitute "DUMMY_TOKEN", which is the worst
                # of the three available behaviours: the run continues, every request is
                # rejected, and rejections are recorded as responses. A target that
                # answered nothing then scores as a target that answered wrongly — an
                # unset environment variable arriving in the report as a finding about
                # somebody's product. An absent measurement and a failed one must never
                # print the same thing (F40), and here the absent one was printing worse.
                where = (
                    f"${auth.token_env} is not set"
                    if auth.token_env
                    else "target.auth.token is empty"
                )
                raise AuthTokenMissing(
                    f"{where}, and target.auth.type is "
                    f"{auth.type!r}.\n\n"
                    f"  Nothing was sent. This is a setup problem, not a finding: with "
                    f"no credential every\n"
                    f"  request would be rejected, and rejections recorded against the "
                    f"target read as answers\n"
                    f"  it got wrong.\n\n"
                    + (
                        f"    export {auth.token_env}=...\n\n"
                        if auth.token_env
                        else "    auth:\n      token: \"...\"\n\n"
                    )
                    +
                    f"  Or set target.auth.type to \"none\" if this endpoint genuinely "
                    f"takes no credential."
                )

            if auth.type == "bearer":
                headers["Authorization"] = f"Bearer {token}"
            elif auth.type == "api_key":
                headers["x-api-key"] = token
            elif auth.type == "basic":
                # Assuming the token is already base64 encoded or formatted appropriately
                headers["Authorization"] = f"Basic {token}"
            elif auth.type == "cookie":
                # The whole cookie header, verbatim: a session product usually needs more
                # than one cookie set, and splitting them across config keys would put
                # half a credential in a file. `AuthConfig.type` is a Literal so an
                # unrecognised scheme is refused at load rather than falling off the end
                # of this chain and sending the probes unauthenticated.
                headers["Cookie"] = token
        return headers

    def _inject_variables(self, template: Any, variables: Dict[str, Any]) -> Any:
        if template is None:
            return None
        if isinstance(template, str):
            # A placeholder that *is* the whole string stands in for the value itself,
            # not for its text. `{{ATTACHMENTS}}` is a list of file references, and a
            # body written as YAML has nowhere to put a list except here — substituting
            # `str(list)` would send a Python repr, single quotes and all, to a JSON API.
            # Only whole-string placeholders qualify: half a list interpolated into a
            # sentence is not a thing any target asked for.
            stripped = template.strip()
            if stripped.startswith("{{") and stripped.endswith("}}"):
                key = stripped[2:-2]
                if key in variables and not isinstance(variables[key], str):
                    return variables[key]
            res = template
            for k, v in variables.items():
                if not isinstance(v, str):
                    continue
                res = res.replace(f"{{{{{k}}}}}", v)
            return res
        elif isinstance(template, dict):
            return {k: self._inject_variables(v, variables) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._inject_variables(item, variables) for item in template]
        else:
            return template

    def _carries_the_answer(self, chunk) -> bool:
        """Whether this frame is one the answer may be read from.

        True for everything unless the config named a frame selector. A stream that
        interleaves reasoning, tool arguments and answer text under one key cannot be
        told apart by JSONPath — filters do not apply to a dict root — so the type is
        matched here instead, where it can be.
        """
        if self.answer_frame_parser is None:
            return True
        match = self.answer_frame_parser.find(chunk)
        wanted = getattr(self.config.response_format, 'answer_frame_value', None)
        return bool(match) and str(match[0].value) == str(wanted)

    def _is_finished(self, body) -> bool:
        """Whether a polled body is the finished answer rather than a record in progress.

        With no `ready_field` this is the pre-existing test: the answer path matched
        something. That test is only safe against targets which do not create the answer
        field until they have an answer to put in it. Against one that writes
        `text: ""` up front it is satisfied on the first poll, and every probe returns
        an empty string that no evaluator can tell from a system with nothing to say.
        """
        if self.ready_parser is None:
            return bool(self.answer_parser.find(body))
        match = self.ready_parser.find(body)
        wanted = getattr(self.config.response_format, 'ready_value', None)
        return bool(match) and str(match[0].value) == str(wanted)

    def _prepare_request(self, endpoint_config, default_payload, variables):
        if isinstance(endpoint_config, str):
            return endpoint_config, "POST", self.headers, {"json": default_payload}
        
        url = self._inject_variables(endpoint_config.url, variables)
        method = endpoint_config.method
        headers = {**self.headers, **endpoint_config.headers}
        
        if endpoint_config.body is not None:
            payload = self._inject_variables(endpoint_config.body, variables)
            if isinstance(payload, (dict, list)):
                return url, method, headers, {"json": payload}
            else:
                return url, method, headers, {"content": payload}
        else:
            if method.upper() == "GET":
                return url, method, headers, {}
            return url, method, headers, {"json": default_payload}

    async def upload_document(self, filename: str, content: str, metadata: Optional[Dict] = None) -> Any:
        endpoint_config = self.config.endpoints.upload
        
        file_field = getattr(endpoint_config, "file_field", None) if not isinstance(endpoint_config, str) else None
        
        default_payload = {
            "filename": filename,
            "content": content,
        }
        if metadata:
            default_payload["metadata"] = metadata
            
        url, method, headers, kwargs = self._prepare_request(
            endpoint_config,
            default_payload=default_payload,
            variables={"FILENAME": filename, "CONTENT": content}
        )
            
        if file_field:
            # Native multipart form upload using httpx
            # Remove content-type from headers so httpx computes the boundary correctly
            headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}
            
            # Since we are sending files, we remove json/content from kwargs
            payload_fields = kwargs.pop("json", None)
            kwargs.pop("content", None)
            # Only a body the config actually wrote. With none, `_prepare_request`
            # hands back the default payload — filename and content — and those are the
            # file, not fields to send beside it.
            declared_body = (
                not isinstance(endpoint_config, str) and endpoint_config.body is not None
            )
            if not (declared_body and isinstance(payload_fields, dict)):
                payload_fields = None
            
            files = {file_field: (filename, content, "text/plain")}
            kwargs["files"] = files
            # Everything else the body named travels as ordinary form fields beside the
            # file. An ingest route that takes the file *and* an owner, a target path or
            # an OCR mode in the same multipart body — Gaius Lex takes all three — was
            # previously unconfigurable: the body was parsed, then dropped on the floor
            # here, and the upload went out missing the fields the target requires.
            form_fields = {
                k: ("" if v is None else str(v))
                for k, v in (payload_fields or {}).items()
                if k != file_field
            }
            if form_fields:
                kwargs["data"] = form_fields
            
            logger.debug(f"Uploading {filename} to {url} using native multipart on field '{file_field}'")
            response = await self.client.request(method, url, headers=headers, **kwargs)
        else:
            logger.debug(f"Uploading {filename} to {url}")
            response = await self.client.request(method, url, headers=headers, **kwargs)
            
        response.raise_for_status()
        return response.json()

    async def delete_document(self, document_id: str) -> None:
        """Remove one document the run uploaded, by identifier.

        The only destructive call in this client, and it exists for one caller: the
        revision phase, replacing a document on a target whose ingest API refuses
        duplicate identifiers. `endpoints.delete` is absent unless a config sets it, so a
        target is never at risk from a default.

        Method defaults to DELETE rather than the client-wide POST. An endpoint named
        `delete` that issued a POST because a default said so is the kind of surprise
        this call cannot afford.
        """
        endpoint_config = self.config.endpoints.delete
        if endpoint_config is None:
            raise ValueError(
                "delete_document called with no `endpoints.delete` configured. "
                "The caller is required to check first — a delete that guesses at a "
                "URL is worse than one that does not happen."
            )

        variables = {"DOCUMENT_ID": document_id}
        if isinstance(endpoint_config, str):
            # Not routed through `_prepare_request`, which substitutes nothing in the
            # string form and attaches a JSON body. Both are wrong here: the identifier
            # is almost always in the path, and a DELETE carrying a body is rejected by
            # enough servers that it cannot be the default for the one destructive call.
            url = self._inject_variables(endpoint_config, variables)
            method, headers, kwargs = "DELETE", self.headers, {}
        else:
            url, method, headers, kwargs = self._prepare_request(
                endpoint_config,
                default_payload={"document_id": document_id},
                variables=variables,
            )
            if not endpoint_config.body:
                kwargs.pop("json", None)
                kwargs.pop("content", None)
            # `EndpointConfig.method` defaults to POST, which is right for every other
            # endpoint and wrong for this one. `model_fields_set` distinguishes an author
            # who wrote `method: POST` from one who wrote nothing — so a deliberate
            # POST-based delete API still works, and silence means DELETE.
            if "method" not in endpoint_config.model_fields_set:
                method = "DELETE"

        logger.debug(f"Deleting document {document_id} at {url}")
        response = await self.client.request(method, url, headers=headers, **kwargs)
        # 404 is success for this caller's purpose: the point is that the identifier is
        # free, and an identifier that was never there is free. Treating it as an error
        # would abort a revision phase over a target that had already expired the
        # document, which is not a failure of anything.
        if response.status_code != 404:
            response.raise_for_status()

    def _extract_json_from_string(self, text: str) -> Optional[str]:
        if not isinstance(text, str):
            return None
        start_brace = text.find('{')
        start_bracket = text.find('[')
        
        start = -1
        if start_brace != -1 and start_bracket != -1:
            start = min(start_brace, start_bracket)
        else:
            start = max(start_brace, start_bracket)
            
        if start != -1:
            return text[start:]
        return None

    async def chat(
        self, query: str, attachments: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Ask one question, optionally naming documents this run already uploaded.

        `attachments` binds to `{{ATTACHMENTS}}` in the chat body as the list of
        `{"filename": ..., "document_id": ...}` the upload phase was issued. It exists
        for products whose chat turn references stored documents per message rather than
        searching a standing index — Eulex posts the ids back under `messages[].files`.
        A config that never writes the placeholder is unaffected.
        """
        import uuid
        req_uuid = str(uuid.uuid4())
        
        # `chat` may be a bare URL string or a full endpoint object (§6.1 allows both,
        # and the README example uses the string form). A string has no `.headers`, so
        # reading it directly made every chat request fail with an AttributeError while
        # uploads — which take the same union — worked fine.
        endpoint_headers = getattr(self.config.endpoints.chat, "headers", None) or {}
        chat_headers = {**self.headers, **endpoint_headers}
        variables: Dict[str, Any] = {
            "QUERY": query,
            "UUID": req_uuid,
            # Always present, empty when nothing was uploaded. A body that names the
            # placeholder must still be valid JSON on an existing-corpus run, and an
            # unsubstituted `{{ATTACHMENTS}}` reaching the wire is not.
            "ATTACHMENTS": list(attachments or []),
        }
        for k, v in chat_headers.items():
            variables[k] = str(v)
            variables[k.replace("-", "_")] = str(v)
        
        url, method, headers, kwargs = self._prepare_request(
            self.config.endpoints.chat,
            default_payload={"query": query},
            variables=variables
        )
        
        receive_endpoint = getattr(self.config.endpoints, "receive", None)
        if receive_endpoint:
            rec_url, rec_method, rec_headers, rec_kwargs = self._prepare_request(
                receive_endpoint,
                default_payload={},
                variables=variables
            )
            if rec_url.startswith("ws://") or rec_url.startswith("wss://"):
                import websockets
                import asyncio

                safe_headers = {k: v for k, v in rec_headers.items() if k.lower() not in ["connection", "upgrade", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions"]}
                
                # Forward cookies from httpx client to websocket
                if self.client.cookies:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in self.client.cookies.items()])
                    safe_headers["Cookie"] = cookie_str
                
                async with websockets.connect(rec_url, additional_headers=safe_headers, open_timeout=60.0) as websocket:
                    init_message = getattr(receive_endpoint, "init_message", None) if not isinstance(receive_endpoint, str) else None
                    if init_message:
                        init_msg_resolved = self._inject_variables(init_message, variables)
                        if isinstance(init_msg_resolved, dict):
                            init_msg_resolved = json.dumps(init_msg_resolved)
                        elif not isinstance(init_msg_resolved, str):
                            init_msg_resolved = str(init_msg_resolved)
                        await websocket.send(init_msg_resolved)
                    elif "socket.io" in rec_url:
                        # Send socket.io namespace connect packet
                        # Flexible: pull from receive.body if configured
                        connect_packet = rec_kwargs.get("content") or rec_kwargs.get("json")
                        if connect_packet:
                            if isinstance(connect_packet, dict):
                                connect_packet = json.dumps(connect_packet)
                            await websocket.send(connect_packet)
                        else:
                            await websocket.send("40")
                        
                    if url.startswith("ws://") or url.startswith("wss://"):
                        # The question goes out on the socket, not over HTTP. Gaius Lex
                        # is this shape: one `wss://…/workflows-agent` connection carries
                        # the send frame *and* the answer, and there is no chat route to
                        # POST to. Without this branch a config would have to name some
                        # unrelated HTTP endpoint as `chat` purely to satisfy the call
                        # below, and the file would then describe a request the target
                        # never receives — §6.1's whole objection.
                        frame = kwargs.get("json", kwargs.get("content"))
                        if isinstance(frame, (dict, list)):
                            frame = json.dumps(frame, ensure_ascii=False)
                        logger.debug(f"Sending query on {url}: {query}")
                        await websocket.send(frame)
                    else:
                        logger.debug(f"Sending query to {url}: {query}")
                        response = await self.client.request(method, url, headers=headers, **kwargs)
                        response.raise_for_status()

                    answer_text = ""
                    citations = []
                    raw_response = {}
                    
                    import time
                    start_time = time.time()
                    
                    while True:
                        if time.time() - start_time > 120.0:
                            logger.error("Websocket receive overall timeout (120s) reached.")
                            break
                        
                        try:
                            current_timeout = 5.0 if answer_text else 45.0
                            message = await asyncio.wait_for(websocket.recv(), timeout=current_timeout)
                            logger.debug(f"Raw WS message: {message}")
                            
                            # Handle Socket.IO Ping
                            if isinstance(message, str) and message == "2":
                                await websocket.send("3")
                                continue
                                
                            if isinstance(message, str) and getattr(self.config.response_format, 'stop_payload_match', None) and self.config.response_format.stop_payload_match in message:
                                logger.debug("Websocket receive stopped by lazy stop_payload_match.")
                                break

                            json_str = self._extract_json_from_string(message)
                            if json_str:
                                chunk = json.loads(json_str)
                                
                                if getattr(self, 'stop_parser', None):
                                    stop_match = self.stop_parser.find(chunk)
                                    if stop_match and str(stop_match[0].value) == getattr(self.config.response_format, 'stop_value', None):
                                        logger.debug("Websocket receive stopped by strict stop_field match.")
                                        break

                                match = (
                                    self.answer_parser.find(chunk)
                                    if self._carries_the_answer(chunk)
                                    else None
                                )
                                if match:
                                    if not self.config.response_format.stream:
                                        answer_text = match[0].value
                                        cit_match = self.citations_parser.find(chunk)
                                        if cit_match and isinstance(cit_match[0].value, list):
                                            citations.extend(cit_match[0].value)
                                        raw_response = chunk
                                        break
                                    else:
                                        answer_text += match[0].value
                                        cit_match = self.citations_parser.find(chunk)
                                        if cit_match and isinstance(cit_match[0].value, list):
                                            citations.extend(cit_match[0].value)
                                        if not isinstance(raw_response, list):
                                            raw_response = []
                                        raw_response.append(chunk)
                        except asyncio.TimeoutError:
                            break
                        except websockets.exceptions.ConnectionClosed:
                            logger.debug("Websocket connection closed by server")
                            break
                        except Exception as e:
                            logger.error(f"Error processing websocket message: {e}")
                            break # Break on unexpected errors to prevent infinite loops
                    
                    # Wait at most 30 seconds for the answer to fully stream if streaming
                    # Wait wait, the timeout inside wait_for handles the idle time.
                    # But if we receive a constant stream of garbage, it could loop forever.
                    # We will rely on ConnectionClosed to break the loop naturally if the server finishes.
                    return {
                        "answer": answer_text,
                        "citations": citations,
                        "raw": raw_response
                    }
            elif rec_method.upper() != "GET":
                # A *driver*, not a poll. Some targets do not generate anything until
                # the client asks them to advance: Justice Pappers creates a question,
                # hands back a uuid, and then produces retrieval, then case law, then
                # the answer, one stage per POST to `…/{uuid}/etape`. Polling such a
                # target with GET reads an empty record forever, because nothing is
                # running.
                #
                # So the receive request is re-issued until a stage carries answer text.
                # Stages that carry none are not failures — the first one answers JSON
                # (the retrieved articles, kept as citations) and the second a stream of
                # case law — they are steps on the way, and the loop keeps going.
                import asyncio
                import time

                fmt = self.config.response_format
                logger.debug(f"Sending query to {url}: {query}")
                response = await self.client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                rec_url, rec_method, rec_headers, rec_kwargs = self._bind_handle(
                    response, receive_endpoint, variables
                )

                deadline = time.monotonic() + fmt.poll_timeout_seconds
                citations: List[Any] = []
                frames: List[Any] = []
                stages = 0
                while time.monotonic() < deadline:
                    stages += 1
                    answer_text, stage_citations, stage_frames = await self._drive_once(
                        rec_method, rec_url, rec_headers, rec_kwargs
                    )
                    citations.extend(stage_citations)
                    frames.extend(stage_frames)
                    if answer_text:
                        return {
                            "answer": answer_text,
                            "citations": citations,
                            "raw": frames,
                        }
                    await asyncio.sleep(fmt.poll_interval_seconds)

                # Same rule as the polling path: an answer that never arrived is a failed
                # measurement, not an empty one (F40). Returning "" would have `generate`
                # write a record indistinguishable from a target declining to answer.
                raise TimeoutError(
                    f"drove {rec_url} through {stages} stages in "
                    f"{fmt.poll_timeout_seconds:g}s and none carried answer text"
                    + (
                        f" on an SSE {fmt.answer_event!r} event"
                        if fmt.answer_event
                        else ""
                    )
                    + ". Raise response_format.poll_timeout_seconds if this target is "
                    "simply slow, or check answer_event/answer_field against a real "
                    "stage; nothing about this probe was measured."
                )
            elif rec_method.upper() == "GET":
                import asyncio
                import time

                fmt = self.config.response_format
                logger.debug(f"Sending query to {url}: {query}")
                response = await self.client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()

                # An asynchronous target hands back a ticket rather than an answer, and
                # the poll URL is not knowable until it does. Re-prepare the receive
                # request with `{{HANDLE}}` bound to what the submit response gave us.
                submitted = {}
                if self.handle_parser is not None:
                    try:
                        submitted = response.json()
                    except Exception as exc:
                        raise RuntimeError(
                            f"response_format.handle_field is set, so the submit "
                            f"response has to be JSON to read the handle out of, and "
                            f"this one is not: {exc}"
                        ) from exc
                    found = self.handle_parser.find(submitted)
                    if not found or found[0].value in (None, ""):
                        raise RuntimeError(
                            f"the submit request succeeded and "
                            f"response_format.handle_field "
                            f"({fmt.handle_field!r}) matched nothing in its body. "
                            f"Without the handle there is no answer to poll for; "
                            f"check the path against a real response before reading "
                            f"anything into this run."
                        )
                    rec_url, rec_method, rec_headers, rec_kwargs = self._prepare_request(
                        receive_endpoint,
                        default_payload={},
                        variables={**variables, "HANDLE": str(found[0].value)},
                    )

                deadline = time.monotonic() + fmt.poll_timeout_seconds
                polls, last_state = 0, None
                while time.monotonic() < deadline:
                    await asyncio.sleep(fmt.poll_interval_seconds)
                    polls += 1
                    resp = await self.client.request(
                        rec_method, rec_url, headers=rec_headers, **rec_kwargs
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()

                    if not self._is_finished(data):
                        if self.ready_parser is not None:
                            state = self.ready_parser.find(data)
                            last_state = state[0].value if state else None
                        continue

                    match = self.answer_parser.find(data)
                    citations = []
                    cit_match = self.citations_parser.find(data)
                    if cit_match and isinstance(cit_match[0].value, list):
                        citations.extend(cit_match[0].value)
                    return {
                        "answer": match[0].value if match else "",
                        "citations": citations,
                        "raw": data,
                    }

                # An answer that never arrived is a failed measurement, not an empty one
                # (F40). Returning "" here would have `generate` write a record that
                # reads exactly like a target declining to answer.
                raise TimeoutError(
                    f"the answer was still not ready after "
                    f"{fmt.poll_timeout_seconds:g}s ({polls} polls of "
                    f"{rec_url}). Last "
                    + (
                        f"{fmt.ready_field} was {last_state!r}, wanted "
                        f"{fmt.ready_value!r}"
                        if self.ready_parser is not None
                        else "poll carried no answer"
                    )
                    + ". Raise response_format.poll_timeout_seconds if this target is "
                    "simply slow; nothing about this probe was measured."
                )

        # Fallback to normal synchronous / SSE processing if receive is not configured
        logger.debug(f"Sending query to {url}: {query}")

        if self.config.response_format.stream:
            answer_text, citations, frames = await self._read_event_stream(
                method, url, headers, kwargs
            )
            return {"answer": answer_text, "citations": citations, "raw": frames}
        else:
            response = await self.client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            data = response.json()

            answer_match = self.answer_parser.find(data)
            answer_text = answer_match[0].value if answer_match else ""

            cit_match = self.citations_parser.find(data)
            citations = cit_match[0].value if cit_match else []

            return {
                "answer": answer_text,
                "citations": citations,
                "raw": data
            }

    def _bind_handle(self, response, receive_endpoint, variables):
        """Re-prepare the receive request with `{{HANDLE}}` bound to the submit's ticket.

        An asynchronous target hands back a ticket rather than an answer, and the poll or
        drive URL is not knowable until it does.
        """
        fmt = self.config.response_format
        if self.handle_parser is None:
            return self._prepare_request(receive_endpoint, {}, variables)
        try:
            submitted = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"response_format.handle_field is set, so the submit response has to be "
                f"JSON to read the handle out of, and this one is not: {exc}"
            ) from exc
        found = self.handle_parser.find(submitted)
        if not found or found[0].value in (None, ""):
            raise RuntimeError(
                f"the submit request succeeded and response_format.handle_field "
                f"({fmt.handle_field!r}) matched nothing in its body. Without the handle "
                f"there is no answer to ask for; check the path against a real response "
                f"before reading anything into this run."
            )
        return self._prepare_request(
            receive_endpoint, {}, {**variables, "HANDLE": str(found[0].value)}
        )

    async def _drive_once(self, method, url, headers, kwargs):
        """Advance one stage, whichever of the two shapes it answers in.

        A stage is JSON or it is an event stream, and which one is not knowable before
        the response arrives — the same URL answers `application/json` for retrieval and
        `text/event-stream` for generation. Dispatching on the content type is what lets
        the retrieved articles be kept as citations from the stage that carries them.
        """
        async with self.client.stream(method, url, headers=headers, **kwargs) as stage:
            stage.raise_for_status()
            content_type = stage.headers.get("content-type", "")
            if "event-stream" in content_type:
                return await self._consume_event_stream(stage)
            await stage.aread()
            try:
                data = stage.json()
            except Exception:
                logger.debug(
                    "stage answered %r, which is not JSON; skipping", content_type
                )
                return "", [], []
        answer_match = self.answer_parser.find(data)
        cit_match = self.citations_parser.find(data)
        citations = (
            cit_match[0].value
            if cit_match and isinstance(cit_match[0].value, list)
            else []
        )
        return (answer_match[0].value if answer_match else ""), citations, [data]

    async def _read_event_stream(self, method, url, headers, kwargs):
        """Read one SSE response into (answer, citations, frames).

        Event names are tracked, not skipped. A stream that types its frames on the
        `event:` line — Justice Pappers sends `message`, `decision`, `enhanced` and
        `complete`, all carrying `{"content": …}` — cannot be told apart by any JSONPath,
        because the name is not in the JSON. `answer_event` names the one to keep and
        `stop_event` the one that ends the read; without them this behaves exactly as it
        did before, which is to say it keeps everything.
        """
        fmt = self.config.response_format
        answer_text = ""
        citations: List[Any] = []
        frames: List[Any] = []
        event_name = None

        async with self.client.stream(method, url, headers=headers, **kwargs) as response:
            response.raise_for_status()
            return await self._consume_event_stream(response)

    async def _consume_event_stream(self, response):
        """The line loop, over a response already open. See `_read_event_stream`.

        Separate because a driven stage cannot re-issue its request to read it: the POST
        that returns the stream is the same POST that advances the target one stage, so
        asking twice would skip one.
        """
        fmt = self.config.response_format
        answer_text = ""
        citations: List[Any] = []
        frames: List[Any] = []
        event_name = None

        async for line in response.aiter_lines():
            line = line.strip()
            if not line:
                # A blank line ends one SSE event. The name does not carry over to
                # the next: an untyped frame after a `message` frame is untyped, and
                # inheriting the previous name would quietly widen the filter.
                event_name = None
                continue

            if line.startswith("event:"):
                event_name = line[6:].strip()
                if fmt.stop_event and event_name == fmt.stop_event:
                    logger.debug("stream ended by stop_event %r", event_name)
                    break
                continue

            if line.startswith("data:"):
                data_str = line[5:].strip()
            elif line.startswith("data "):
                data_str = line[5:].strip()
            elif line.startswith("id:") or line.startswith("retry:"):
                continue
            else:
                data_str = line

            if data_str == "[DONE]":
                break

            if fmt.stop_payload_match and fmt.stop_payload_match in data_str:
                logger.debug("HTTP stream stopped by lazy stop_payload_match.")
                break

            if not data_str:
                continue

            # Only the decode is guarded, and only against a frame that is not JSON —
            # a stream carries comments, keep-alives and a provider's own framing
            # alongside the payload, and one of those is skipped rather than ending
            # the read.
            #
            # Everything below the decode is deliberately outside the guard. A raise
            # there is a bug in extraction or a config whose paths do not fit this
            # target, and swallowing it yields an empty answer that reads exactly
            # like a system with nothing to say (F40). `generate` records a raise as
            # a transport error, which is the honest record of a read that failed.
            json_str = self._extract_json_from_string(data_str)
            try:
                chunk = json.loads(json_str if json_str else data_str)
            except json.JSONDecodeError:
                logger.debug(
                    "skipping a stream frame that is not JSON: %.120r", data_str
                )
                continue

            if self.stop_parser is not None:
                stop_match = self.stop_parser.find(chunk)
                if stop_match and str(stop_match[0].value) == fmt.stop_value:
                    logger.debug("HTTP stream stopped by strict stop_field match.")
                    break

            wanted_event = fmt.answer_event is None or event_name == fmt.answer_event
            if wanted_event and self._carries_the_answer(chunk):
                match = self.answer_parser.find(chunk)
                if match:
                    answer_text += match[0].value

            cit_match = self.citations_parser.find(chunk)
            if cit_match and isinstance(cit_match[0].value, list):
                citations.extend(cit_match[0].value)
            frames.append(chunk)

        return answer_text, citations, frames

    async def close(self):
        await self.client.aclose()
