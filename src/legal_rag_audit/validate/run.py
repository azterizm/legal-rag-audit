"""`validate` — three neutral probes, the raw body, and what the config extracted (§7.1).

Wrong JSONPath is our own documented leading cause of false positives, and an empty
extracted string scored as a hallucination is a finding we would have to retract in
front of the buyer. This mode exists to make that failure cost two minutes instead of
an engagement.

It scores nothing, writes nothing, and asks nothing from the battery. What it does is
send three throwaway queries, print what came back beside what the configured paths
pulled out of it, and name — by code, with a remedy — every condition in §7.1's table
that would otherwise reach the report as a finding about somebody's product.

**It runs its own transfers rather than calling `TargetClient.chat`.** The two want
different things from the same request. `chat` wants an answer and discards the wrapper;
this wants the wrapper, the frame count, the status line, whether the stream terminated
on the target's say-so or on our deadline, and how long each stage took. It shares the
parts of the client where a config error actually hides — the auth headers, the request
templating in `_prepare_request`, the compiled JSONPath parsers — so what is validated
is the config `generate` will run with, not a second implementation of it.

The one deliberate difference is the deadline. `TargetClient` waits 60 seconds because a
real answer sometimes takes that long; this waits `--timeout` (15s by default) because
the whole value of the mode is that it comes back quickly with a diagnosis.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Optional

from ..config import AuditConfig
from ..transport import TargetClient
from . import diagnose
from .diagnose import Diagnosis
from .neutral import (
    NEUTRAL_DOCUMENT_FILENAME,
    NEUTRAL_DOCUMENT_ID,
    NEUTRAL_DOCUMENT_TEXT,
    NEUTRAL_PROBES,
)
from .suggest import answer_candidates, citation_candidates

#: How much of the body to keep. The point is to show the reader the shape of what came
#: back, and a megabyte of retrieval debug output in a terminal is not that.
RAW_LIMIT = 4000

#: Above this, the projected battery duration gets a named diagnosis rather than just a
#: printed number. §7.1 says "a multi-hour run"; an hour is where the conversation has
#: to happen with the target rather than after it.
PROJECTION_ALERT_SECONDS = 3600

#: How many probes the battery asks, per pass. **A number, not an import** — importing
#: `probes.battery` to count it would be the one import edge §7.1 forbids, and the
#: warning there is about exactly this kind of convenience.
#:
#: `tests/test_validate.py` compares this against `len(build_probes())` and fails the
#: build when they part company. The constant can go stale; the projection it feeds
#: cannot go stale silently.
BATTERY_PROBE_COUNT = 19


@dataclass
class Observation:
    """One neutral query and everything we could see about what came back."""

    probe_id: str
    query: str
    purpose: str
    url: str = ""
    #: Where the answer was listened for, when that is somewhere other than `url`. A
    #: websocket that refuses the connection is a problem with *this* address, and a
    #: diagnosis naming the chat endpoint would send the reader to the wrong line of
    #: their config.
    receive_url: str = ""
    method: str = "POST"
    transport: str = "json"
    #: Websockets only. False — the connection never opened. True — it opened, and
    #: whatever went wrong afterwards is a different problem with a different remedy.
    connected: Optional[bool] = None
    http_status: Optional[int] = None
    retry_after: Optional[str] = None
    elapsed_ms: int = 0
    raw: str = ""
    truncated: bool = False
    parsed: Any = None
    frames: int = 0
    #: Streams only, and three-valued rather than boolean because two of the three are
    #: fine and one is the §7.1 condition.
    #:
    #: `terminator` — the target said it was done, which is what the config expects.
    #: `connection close` — the target closed the stream without one. Also fine: the
    #: transport reads to exhaustion, so the answer arrives whole. Worth printing,
    #: because a configured `stop_payload_match` that never fires is a config nobody
    #: is using.
    #: `deadline` — *our* clock ended it, not theirs. That is the failure.
    ended_by: Optional[str] = None
    answer: Optional[str] = None
    citations: Optional[list] = None
    error: Optional[str] = None

    @property
    def extracted(self) -> bool:
        return bool((self.answer or "").strip())


@dataclass
class UploadObservation:
    attempted: bool
    ok: bool = False
    identifier: Optional[str] = None
    body: str = ""
    error: Optional[str] = None
    skipped_because: Optional[str] = None


@dataclass
class Validation:
    target_name: str
    answer_field: str
    citations_field: str
    observations: list[Observation] = field(default_factory=list)
    upload: Optional[UploadObservation] = None
    retrieval: Optional[str] = None
    diagnoses: list[Diagnosis] = field(default_factory=list)
    median_ms: Optional[int] = None
    probe_count: int = BATTERY_PROBE_COUNT
    probe_count_source: str = "the count this build ships"
    passes: int = 1

    @property
    def projected_seconds(self) -> Optional[float]:
        if self.median_ms is None:
            return None
        return self.median_ms / 1000 * self.probe_count * self.passes

    @property
    def blocked(self) -> bool:
        """Whether a run started now would be measuring the target or measuring us."""
        return any(d.blocking for d in self.diagnoses)


def _variables(client: TargetClient, query: str, headers: dict) -> dict[str, str]:
    """The same substitution table `TargetClient.chat` builds.

    Copied rather than shared because it is four lines and reaching into `chat` for it
    would mean running the request path this module exists to observe from outside.
    Kept honest by a test that asserts the two tables agree.
    """
    import uuid

    variables = {"QUERY": query, "UUID": uuid.uuid4().hex}
    for key, value in headers.items():
        variables[key] = str(value)
        variables[key.replace("-", "_")] = str(value)
    return variables


def _clip(text: str) -> tuple[str, bool]:
    return (text, False) if len(text) <= RAW_LIMIT else (text[:RAW_LIMIT], True)


def _decode(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _terminator(config, payload: str, parsed: Any, stop_parser) -> bool:
    """Did the target say this frame was the last one?"""
    fmt = config.target.response_format
    if payload.strip() == "[DONE]":
        return True
    if fmt.stop_payload_match and fmt.stop_payload_match in payload:
        return True
    if stop_parser is not None and parsed is not None:
        found = stop_parser.find(parsed)
        if found and str(found[0].value) == str(fmt.stop_value):
            return True
    return False


async def _observe_json(config, client, http, probe, timeout) -> Observation:
    obs = Observation(probe.probe_id, probe.text, probe.purpose, transport="json")
    headers = getattr(config.target.endpoints.chat, "headers", None) or {}
    merged = {**client.headers, **headers}
    url, method, request_headers, kwargs = client._prepare_request(
        config.target.endpoints.chat,
        default_payload={"query": probe.text},
        variables=_variables(client, probe.text, merged),
    )
    obs.url, obs.method = url, method

    t0 = time.monotonic()
    try:
        response = await http.request(method, url, headers=request_headers, **kwargs)
    except Exception as e:
        obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
        obs.error = f"{type(e).__name__}: {e}"
        return obs

    obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
    obs.http_status = response.status_code
    obs.retry_after = response.headers.get("Retry-After")
    obs.raw, obs.truncated = _clip(response.text)
    obs.parsed = _decode(response.text)
    _extract(client, obs)
    return obs


async def _observe_sse(config, client, http, probe, timeout) -> Observation:
    obs = Observation(probe.probe_id, probe.text, probe.purpose, transport="sse")
    headers = getattr(config.target.endpoints.chat, "headers", None) or {}
    merged = {**client.headers, **headers}
    url, method, request_headers, kwargs = client._prepare_request(
        config.target.endpoints.chat,
        default_payload={"query": probe.text},
        variables=_variables(client, probe.text, merged),
    )
    obs.url, obs.method = url, method

    collected: list[str] = []
    answer = ""
    citations: list = []
    t0 = time.monotonic()
    try:
        async with http.stream(
            method, url, headers=request_headers, **kwargs
        ) as response:
            obs.http_status = response.status_code
            obs.retry_after = response.headers.get("Retry-After")
            if response.status_code >= 400:
                await response.aread()
                obs.raw, obs.truncated = _clip(response.text)
                obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
                return obs

            obs.ended_by = "connection close"
            async for line in response.aiter_lines():
                if time.monotonic() - t0 > timeout:
                    obs.ended_by = "deadline"
                    break
                line = line.strip()
                if not line or line.startswith(("id:", "event:", "retry:")):
                    continue
                payload = line[5:].strip() if line.startswith("data:") else line
                obs.frames += 1
                if len(collected) < 40:
                    collected.append(payload)

                chunk = _decode(payload)
                if _terminator(config, payload, chunk, client.stop_parser):
                    obs.ended_by = "terminator"
                    break
                if chunk is not None:
                    # The frame selector has to be applied here too, or this mode lies
                    # about the one thing it exists to show. `generate` reads the answer
                    # only from frames whose type matches `answer_frame_value`; a
                    # `validate` that skipped that check previewed a different extraction
                    # than the run would perform, in both directions. Against a stream
                    # whose `*_end` frames had been renamed it printed the *thinking*
                    # text under "extracted" while `generate` would have recorded an
                    # empty answer; against a healthy interleaved stream it would
                    # concatenate reasoning into a preview that looked fine. Either way
                    # the operator reads a preview of a run that will not happen, which
                    # is exactly what §7.1 puts this mode in front of the battery to
                    # prevent.
                    if client._carries_the_answer(chunk):
                        found = client.answer_parser.find(chunk)
                        if found:
                            answer += str(found[0].value)
                    cited = client.citations_parser.find(chunk)
                    if cited and isinstance(cited[0].value, list):
                        citations.extend(cited[0].value)
    except Exception as e:
        obs.error = f"{type(e).__name__}: {e}"

    obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
    obs.raw, obs.truncated = _clip("\n".join(collected))
    # The parsed body of a stream is the last frame we could decode. It is what the
    # suggestion heuristic gets to work with, and saying so beats presenting it as
    # though the whole response had one shape.
    for payload in reversed(collected):
        decoded = _decode(payload)
        if decoded is not None:
            obs.parsed = decoded
            break
    obs.answer = answer or None
    obs.citations = citations or None
    return obs


async def _observe_ws(config, client, http, probe, timeout) -> Observation:
    """Handshake, subscribe, fire the query on the side channel, read frames.

    The websocket configuration is the least visible part of §6.1 and the most likely
    to be wrong, because nothing about it fails loudly: a bad `init_message` produces a
    connection that stays open and says nothing, which is indistinguishable from a
    system that declined to answer.
    """
    import websockets

    obs = Observation(probe.probe_id, probe.text, probe.purpose, transport="websocket")
    receive = config.target.endpoints.receive
    headers = getattr(config.target.endpoints.chat, "headers", None) or {}
    merged = {**client.headers, **headers}
    variables = _variables(client, probe.text, merged)

    rec_url, _, rec_headers, rec_kwargs = client._prepare_request(
        receive, default_payload={}, variables=variables
    )
    url, method, request_headers, kwargs = client._prepare_request(
        config.target.endpoints.chat,
        default_payload={"query": probe.text},
        variables=variables,
    )
    obs.url, obs.method, obs.receive_url = url, method, rec_url
    obs.connected = False

    hop_by_hop = {
        "connection",
        "upgrade",
        "sec-websocket-key",
        "sec-websocket-version",
        "sec-websocket-extensions",
    }
    safe = {k: v for k, v in rec_headers.items() if k.lower() not in hop_by_hop}

    collected: list[str] = []
    answer = ""
    citations: list = []
    t0 = time.monotonic()
    try:
        async with websockets.connect(
            rec_url, additional_headers=safe, open_timeout=timeout
        ) as socket:
            obs.connected = True
            init = getattr(receive, "init_message", None)
            if init is not None:
                resolved = client._inject_variables(init, variables)
                await socket.send(
                    json.dumps(resolved)
                    if isinstance(resolved, (dict, list))
                    else str(resolved)
                )

            response = await http.request(
                method, url, headers=request_headers, **kwargs
            )
            obs.http_status = response.status_code

            obs.ended_by = "deadline"
            while time.monotonic() - t0 < timeout:
                remaining = timeout - (time.monotonic() - t0)
                try:
                    message = await asyncio.wait_for(socket.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                except websockets.exceptions.ConnectionClosed:
                    obs.ended_by = "connection close"
                    break

                text = message if isinstance(message, str) else message.decode(
                    "utf-8", "replace"
                )
                if text == "2":  # socket.io heartbeat, not a frame of the answer
                    await socket.send("3")
                    continue
                obs.frames += 1
                if len(collected) < 40:
                    collected.append(text)

                chunk = _decode(text) or _decode(
                    client._extract_json_from_string(text) or ""
                )
                if _terminator(config, text, chunk, client.stop_parser):
                    obs.ended_by = "terminator"
                    break
                if chunk is not None:
                    # Same frame selector as the SSE path above, for the same reason.
                    if client._carries_the_answer(chunk):
                        found = client.answer_parser.find(chunk)
                        if found:
                            answer += str(found[0].value)
                        if not config.target.response_format.stream:
                            obs.ended_by = "terminator"
                            cited = client.citations_parser.find(chunk)
                            if cited and isinstance(cited[0].value, list):
                                citations.extend(cited[0].value)
                            break
                    cited = client.citations_parser.find(chunk)
                    if cited and isinstance(cited[0].value, list):
                        citations.extend(cited[0].value)
    except Exception as e:
        obs.error = f"{type(e).__name__}: {e}"

    obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
    obs.raw, obs.truncated = _clip("\n".join(collected))
    for payload in reversed(collected):
        decoded = _decode(payload)
        if decoded is not None:
            obs.parsed = decoded
            break
    obs.answer = answer or None
    obs.citations = citations or None
    return obs


async def _observe_poll(config, client, http, probe, timeout) -> Observation:
    """POST the query, then poll the `receive` endpoint until the answer appears."""
    obs = Observation(probe.probe_id, probe.text, probe.purpose, transport="poll")
    obs.ended_by = "deadline"
    headers = getattr(config.target.endpoints.chat, "headers", None) or {}
    merged = {**client.headers, **headers}
    variables = _variables(client, probe.text, merged)

    url, method, request_headers, kwargs = client._prepare_request(
        config.target.endpoints.chat,
        default_payload={"query": probe.text},
        variables=variables,
    )
    rec_url, rec_method, rec_headers, rec_kwargs = client._prepare_request(
        config.target.endpoints.receive, default_payload={}, variables=variables
    )
    obs.url, obs.method, obs.receive_url = url, method, rec_url

    t0 = time.monotonic()
    try:
        posted = await http.request(method, url, headers=request_headers, **kwargs)
        obs.http_status = posted.status_code
        obs.retry_after = posted.headers.get("Retry-After")
        if posted.status_code >= 400:
            obs.raw, obs.truncated = _clip(posted.text)
            obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
            obs.ended_by = None
            return obs

        # An asynchronous target's poll URL is not knowable before the submit, and this
        # command's promise is that it does what `generate` will do. Resolving the
        # handle here rather than only in the transport is what makes that true — the
        # first version of this polled a URL with `{{HANDLE}}` still in it, reported
        # eleven 404s as *the answer never arrived*, and would have sent someone
        # rewriting a config that was correct.
        if client.handle_parser is not None:
            found = client.handle_parser.find(_decode(posted.text) or {})
            if not found or found[0].value in (None, ""):
                obs.raw, obs.truncated = _clip(posted.text)
                obs.error = (
                    f"response_format.handle_field "
                    f"({config.target.response_format.handle_field!r}) matched nothing "
                    f"in the submit response, so there is no address to poll"
                )
                obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
                obs.ended_by = None
                return obs
            rec_url, rec_method, rec_headers, rec_kwargs = client._prepare_request(
                config.target.endpoints.receive,
                default_payload={},
                variables={**variables, "HANDLE": str(found[0].value)},
            )
            obs.receive_url = rec_url

        interval = getattr(config.target.response_format, "poll_interval_seconds", 1.0)
        while time.monotonic() - t0 < timeout:
            await asyncio.sleep(interval)
            obs.frames += 1
            polled = await http.request(
                rec_method, rec_url, headers=rec_headers, **rec_kwargs
            )
            if polled.status_code != 200:
                continue
            obs.raw, obs.truncated = _clip(polled.text)
            obs.parsed = _decode(polled.text)
            # `_is_finished`, not "the answer path matched": a target that creates the
            # answer field empty and fills it in later satisfies the latter on the first
            # poll, and `validate` would bless a config that returns nothing but empty
            # strings.
            if obs.parsed is not None and client._is_finished(obs.parsed):
                _extract(client, obs)
                obs.ended_by = "terminator"
                break
    except Exception as e:
        obs.error = f"{type(e).__name__}: {e}"

    obs.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return obs


def _extract(client: TargetClient, obs: Observation) -> None:
    """Run the configured paths over the body. Exactly what `generate` will do."""
    if obs.parsed is None:
        return
    found = client.answer_parser.find(obs.parsed)
    obs.answer = str(found[0].value) if found else None
    cited = client.citations_parser.find(obs.parsed)
    obs.citations = (
        cited[0].value if cited and isinstance(cited[0].value, list) else None
    )


async def _observe_upload(config, client, http) -> UploadObservation:
    """Send one neutral file and see whether an identifier comes back."""
    endpoint = config.target.endpoints.upload
    file_field = (
        getattr(endpoint, "file_field", None)
        if not isinstance(endpoint, str)
        else None
    )
    url, method, headers, kwargs = client._prepare_request(
        endpoint,
        default_payload={
            "filename": NEUTRAL_DOCUMENT_FILENAME,
            "content": NEUTRAL_DOCUMENT_TEXT,
            "metadata": {"id": NEUTRAL_DOCUMENT_ID},
        },
        variables={
            "FILENAME": NEUTRAL_DOCUMENT_FILENAME,
            "CONTENT": NEUTRAL_DOCUMENT_TEXT,
        },
    )
    if file_field:
        headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        kwargs.pop("json", None)
        kwargs.pop("content", None)
        kwargs["files"] = {
            file_field: (
                NEUTRAL_DOCUMENT_FILENAME,
                NEUTRAL_DOCUMENT_TEXT,
                "text/plain",
            )
        }

    try:
        response = await http.request(method, url, headers=headers, **kwargs)
    except Exception as e:
        return UploadObservation(
            attempted=True, ok=False, error=f"{type(e).__name__}: {e}"
        )

    body, _ = _clip(response.text)
    if response.status_code >= 400:
        return UploadObservation(
            attempted=True,
            ok=False,
            body=body,
            error=f"HTTP {response.status_code}",
        )

    parsed = _decode(response.text)
    identifier = None
    if isinstance(parsed, dict):
        for key in ("id", "document_id", "doc_id", "uuid"):
            if parsed.get(key):
                identifier = str(parsed[key])
                break
    return UploadObservation(
        attempted=True, ok=True, identifier=identifier, body=body
    )


async def _observe_retrieval(config, client, http) -> Optional[str]:
    """One neutral query against the retrieval endpoint, if there is one."""
    endpoint = config.target.endpoints.retrieval
    if endpoint is None:
        return None
    query = NEUTRAL_PROBES[0].text
    try:
        url, method, headers, kwargs = client._prepare_request(
            endpoint, default_payload={"query": query}, variables={"QUERY": query}
        )
        response = await http.request(method, url, headers=headers, **kwargs)
    except Exception as e:
        return f"unreachable — {type(e).__name__}: {e}"
    if response.status_code != 200:
        return f"HTTP {response.status_code}"
    parsed = _decode(response.text)
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
        return f"{len(parsed['data'])} chunks under `data`"
    return "200, but no `data` list in the body — chunks will not be captured"


def _choose(config) -> Any:
    receive = config.target.endpoints.receive
    if receive is not None:
        url = receive if isinstance(receive, str) else receive.url
        if url.startswith(("ws://", "wss://")):
            return _observe_ws
        return _observe_poll
    if config.target.response_format.stream:
        return _observe_sse
    return _observe_json


async def _run(
    config: AuditConfig, timeout: float, skip_upload: bool
) -> tuple[list[Observation], Optional[UploadObservation], Optional[str]]:
    import httpx

    client = TargetClient(config.target)
    observe = _choose(config)
    # Our own client, on a short leash. `TargetClient`'s 60s is right for a real answer
    # and wrong for a mode whose value is that it comes back fast with a diagnosis.
    http = httpx.AsyncClient(timeout=timeout, headers=client.headers)
    try:
        upload = None
        if config.target.endpoints.upload is None:
            # Existing-corpus mode uploads nothing and needs no upload endpoint (F25),
            # so a config in that mode legitimately has none. Reaching for it anyway
            # crashed `validate` with an AttributeError — the one command whose whole
            # job is to tell someone their config is wrong before they spend a run.
            upload = UploadObservation(
                attempted=False,
                skipped_because="no upload endpoint is configured, which is correct "
                "for a run against the target's own index — nothing is uploaded, so "
                "whether uploads issue document identifiers does not arise",
            )
        elif not skip_upload:
            upload = await _observe_upload(config, client, http)
        else:
            upload = UploadObservation(
                attempted=False,
                skipped_because="--skip-upload was given, so whether the upload "
                "endpoint issues document identifiers is unknown",
            )
        observations = [
            await observe(config, client, http, probe, timeout)
            for probe in NEUTRAL_PROBES
        ]
        retrieval = await _observe_retrieval(config, client, http)
    finally:
        await http.aclose()
        await client.close()
    return observations, upload, retrieval


def _diagnose(
    config: AuditConfig, result: Validation
) -> list[Diagnosis]:
    found: list[Diagnosis] = []
    fmt = config.target.response_format
    token_env = config.target.auth.token_env

    # One diagnosis per condition, not one per probe. Three identical auth rejections
    # are one problem, and printing it three times buries the two below it.
    seen: set[str] = set()

    def add(diagnosis: Diagnosis) -> None:
        if diagnosis.code not in seen:
            seen.add(diagnosis.code)
            found.append(diagnosis)

    for obs in result.observations:
        # A websocket that never opened is a problem with the *receive* address, and
        # it is checked first so the diagnosis names that URL. The generic unreachable
        # branch below reads `obs.url`, which is the chat endpoint — a reader sent to
        # the wrong line of their config is worse off than one sent nowhere.
        if obs.connected is False:
            add(
                diagnose.unreachable(
                    obs.probe_id,
                    obs.receive_url,
                    obs.error or "the websocket connection did not open",
                )
            )
            continue
        if obs.error and obs.http_status is None:
            add(diagnose.unreachable(obs.probe_id, obs.url, obs.error))
            continue
        if obs.http_status in (401, 403, 407):
            add(diagnose.auth_rejected(obs.http_status, obs.probe_id, token_env))
            continue
        if obs.http_status == 429:
            add(
                diagnose.rate_limited(obs.http_status, obs.probe_id, obs.retry_after)
            )
            continue
        if obs.http_status is not None and obs.http_status >= 400:
            add(diagnose.bad_status(obs.http_status, obs.probe_id))
            continue
        if obs.transport == "websocket" and obs.frames == 0:
            add(
                diagnose.handshake_failed(
                    obs.probe_id,
                    obs.receive_url,
                    obs.error
                    or f"connected, sent the init frame, and received nothing in "
                    f"{obs.elapsed_ms / 1000:.0f}s",
                )
            )
            continue
        if obs.transport == "poll" and obs.ended_by == "deadline":
            # Not `stream_never_terminated`: there is no stream and no terminator to
            # configure, so that remedy would point at a key this config does not use.
            add(
                diagnose.answer_never_arrived(
                    obs.probe_id, obs.elapsed_ms / 1000, obs.frames
                )
            )
            continue
        if obs.ended_by == "deadline":
            add(
                diagnose.stream_never_terminated(
                    obs.probe_id,
                    obs.elapsed_ms / 1000,
                    obs.frames,
                    fmt.stop_payload_match,
                )
            )

    # Extraction is diagnosed last, and only when the responses actually arrived. A 401
    # produces three empty answers and no citations, and reporting those as two path
    # problems would send the operator to two config keys that are probably correct
    # while the real cause sits above them. Same rule as the report itself: an absent
    # measurement and a failed one must never print the same (F40).
    transport_failed = bool(seen)

    if not transport_failed and not any(o.extracted for o in result.observations):
        sample = next(
            (o for o in result.observations if o.parsed is not None),
            result.observations[0] if result.observations else None,
        )
        add(
            diagnose.answer_not_extracted(
                sample.probe_id if sample else "validate-1",
                fmt.answer_field,
                sample is not None and sample.parsed is not None,
                [c.path for c in answer_candidates(sample.parsed if sample else None)],
            )
        )

    if (
        not transport_failed
        and result.observations
        and not any(o.citations for o in result.observations)
    ):
        sample = next((o for o in result.observations if o.parsed is not None), None)
        add(
            diagnose.citations_not_extracted(
                fmt.citations_field,
                [c.path for c in citation_candidates(sample.parsed if sample else None)],
            )
        )

    upload = result.upload
    if upload and upload.attempted and upload.ok and not upload.identifier:
        add(diagnose.upload_no_identifier(upload.body or "(empty body)"))

    projected = result.projected_seconds
    if projected is not None and projected >= PROJECTION_ALERT_SECONDS:
        add(
            diagnose.run_too_long(
                result.median_ms or 0,
                result.probe_count,
                result.passes,
                projected / 3600,
            )
        )

    return found


def validate(
    config: AuditConfig,
    *,
    timeout: float = 15.0,
    passes: Optional[int] = None,
    probe_count: Optional[int] = None,
    probe_count_source: Optional[str] = None,
    skip_upload: bool = False,
) -> Validation:
    """Send the neutral probes, observe everything, name what is wrong. Writes nothing.

    Returns rather than prints, so the same run can be rendered for a terminal and
    asserted against in a test without the test parsing prose.
    """
    result = Validation(
        target_name=config.target.name,
        answer_field=config.target.response_format.answer_field,
        citations_field=config.target.response_format.citations_field,
        passes=passes if passes is not None else config.battery.passes,
        probe_count=probe_count or BATTERY_PROBE_COUNT,
        probe_count_source=probe_count_source or "the count this build ships",
    )

    observations, upload, retrieval = asyncio.run(_run(config, timeout, skip_upload))
    result.observations = observations
    result.upload = upload
    result.retrieval = retrieval

    # Any 2xx, not 200 exactly. An asynchronous target answers the submit with 201
    # Created — it created a message and has not answered yet — and three probes that
    # all worked were reported as *no query returned 200*, withholding the run-length
    # projection from precisely the kind of target that most needs one.
    timings = [
        o.elapsed_ms
        for o in observations
        if o.http_status is not None and 200 <= o.http_status < 300
    ]
    result.median_ms = int(median(timings)) if timings else None

    result.diagnoses = _diagnose(config, result)
    return result
