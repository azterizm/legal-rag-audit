"""The run configuration (§6.1), and what it refuses to accept.

Every model here sets `extra="forbid"`, which is a deliberate reversal of pydantic's
default and the reason this docstring exists. Ignoring an unrecognised key means a config
can ask for something the run does not do, and say so in writing, and nobody finds out —
the tool would be exhibiting in its own setup the failure class §1 says it exists to find
in other people's systems. A key that does nothing is a defect whether it appears in a
retrieval pipeline or in the YAML that configures the audit of one.

`_refuse_v1_keys` on `CorpusConfig` and `AuditConfig` catches the two settings that
actually moved and names them, because "extra inputs are not permitted" tells an operator
that something is wrong and not what to do about it (NF9).
"""

import os
from typing import Any, Dict, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .authorisation import Authorisation

#: Applied to every model in this file. See the module docstring.
STRICT = ConfigDict(extra="forbid")


class EndpointConfig(BaseModel):
    model_config = STRICT

    url: str
    method: str = "POST"
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Any = None
    file_field: Optional[str] = None
    init_message: Any = None

class EndpointsConfig(BaseModel):
    model_config = STRICT

    chat: Union[str, EndpointConfig]
    receive: Optional[Union[str, EndpointConfig]] = None
    #: Optional since Phase G, and that is F25 rather than a convenience. Existing-corpus
    #: mode probes the target's own index and uploads nothing, so requiring the key would
    #: have meant the half of §9.1 that exists to need no upload endpoint could not be
    #: configured without naming one. `generate` refuses a run that has documents to send
    #: and nowhere to send them, which is the check that actually matters.
    upload: Optional[Union[str, EndpointConfig]] = None
    retrieval: Optional[Union[str, EndpointConfig]] = None
    #: **The only endpoint that destroys anything.** Optional, and absent by default, so
    #: the tool is additive on someone else's index unless a config says otherwise.
    #:
    #: It exists because `index_freshness` replaces a document mid-run (§8.2 #4), and an
    #: ingest API that refuses duplicate identifiers cannot be made to replace anything by
    #: uploading again — Vectara's `upload_file` answers 409, and it is not alone. Without
    #: this the family is unrunnable against a create-only target rather than merely
    #: awkward.
    #:
    #: Used in exactly one place: the revision phase, against the revised documents, by
    #: identifier. It is never called on a document this run did not upload, and
    #: `tests/test_generate_delete.py` is what holds that true. When it is absent the
    #: revision phase skips loudly and index freshness reports NOT_CAPTURED, which is the
    #: honest answer and the safe default.
    #:
    #: `{{DOCUMENT_ID}}` in the url or body is replaced with the document's identifier.
    delete: Optional[Union[str, EndpointConfig]] = None

class AuthConfig(BaseModel):
    """How the run authenticates to the target, and where the credential comes from.

    `type` is a `Literal` rather than a free string, and that is the same argument as
    `extra="forbid"` above. `_build_auth_headers` matched the four known values and fell
    off the end of the chain for anything else — so `type: cookie` fetched the token,
    attached no header, and sent every probe unauthenticated. The target answers 401, the
    401s are recorded as responses, and a target that refused to talk to us scores as one
    that answered badly. That is F40 again: an absent measurement printing as a failed
    one, out of a typo.

    `cookie` is here because a browser-session product has no other credential to offer.
    It is a header like the rest — the point of naming it is that the token still lives in
    the environment and never in the config file.
    """

    model_config = STRICT

    type: Literal["none", "bearer", "api_key", "basic", "cookie"] = "none"
    #: The environment variable holding the credential. The safe spelling, and the one to
    #: reach for by default: a config is committed, pasted into an issue and copied
    #: between runs, and a secret in one of those is a secret in all of them.
    token_env: Optional[str] = None
    #: The credential itself, in the file. Deliberately available and deliberately
    #: second, for a self-contained run config that is thrown away rather than kept — a
    #: short-lived browser session token in a file deleted after the run is a different
    #: risk from an API key in a committed config, and refusing the spelling outright
    #: just pushes operators into `export` lines their shell history keeps.
    #:
    #: What it does not touch: nothing here reaches an artefact. The manifest records a
    #: *hash* of the config, never its content (`provenance.emit`), so a token in this
    #: field does not travel with the report. The file itself is yours to delete.
    token: Optional[str] = None

    @model_validator(mode="after")
    def _a_scheme_needs_somewhere_to_read_the_credential_from(self) -> "AuthConfig":
        if self.token is not None and not self.token.strip():
            raise ValueError(
                "auth.token is set to a blank string. A credential lost to a bad "
                "copy-paste is caught here\n"
                "  or not at all: the run would send an empty Bearer header and record "
                "every rejection as\n"
                "  an answer the target gave. Remove the key, or paste the token."
            )
        if self.token is not None:
            # Tokens arrive from a clipboard and a YAML block scalar; a trailing newline
            # in an Authorization header is a 400 from some servers and a silent
            # mismatch on others.
            object.__setattr__(self, "token", self.token.strip())
        if self.type != "none" and self.token_env and self.token:
            raise ValueError(
                "auth.token and auth.token_env are both set. Which one is live cannot "
                "be read off the file,\n"
                "  and the wrong guess sends a stale credential — whereupon the "
                "target's rejections are\n"
                "  recorded as answers it gave. Keep one."
            )
        if self.type != "none" and not self.token_env and not self.token:
            raise ValueError(
                f"auth.type is {self.type!r} but auth.token_env is not set.\n"
                "  Nothing would be sent to authenticate, and the target's rejections "
                "would be recorded\n"
                "  as answers it gave. Name the environment variable holding the "
                "credential:\n"
                "    auth:\n"
                f"      type: {self.type}\n"
                "      token_env: TARGET_API_KEY\n"
                "  Or, for a run config that is deleted after the run, the credential "
                "itself:\n"
                "    auth:\n"
                f"      type: {self.type}\n"
                '      token: "..."\n'
                "  Or set type: none if this endpoint genuinely takes no credential."
            )
        return self

class ResponseFormatConfig(BaseModel):
    """Where the answer is in what came back, and which parts of it are the answer.

    `answer_frame_field` / `answer_frame_value` exist because a streaming target's frames
    are *typed*, and a JSONPath cannot see the type. `jsonpath_ng` filter expressions
    (`$[?(@.type=="text")]`) apply to arrays, not to the dict that one SSE frame is, so
    the only way to select a frame used to be to find a path that happened to exist on
    the frames you wanted and on no others.

    That is a guess dressed as a rule, and it failed on the second live target. Its
    stream carries reasoning, tool arguments and answer text under the same key: the
    obvious path collected 2,210 characters where the answer was 654, chain-of-thought
    scored as an answer. The path chosen instead — the final message's second content
    block, after the thinking block — was verified byte-exact against a capture and then
    matched nothing on the one probe where that model returned no thinking block. The
    answer was in the file the whole time, 921 characters of it, and the run recorded a
    failure (correctly, per the guard in `generate`) rather than an answer.

    With these two fields the same target is configured by saying what is true:

        answer_field: "$.content"
        answer_frame_field: "$.type"
        answer_frame_value: "text_end"

    Frames whose `answer_frame_field` does not equal `answer_frame_value` are not
    consulted for the answer at all. Both must be set together — one alone is a
    half-written rule, and the validator below refuses it rather than silently ignoring
    it (§6.1: a config that asks for something the run does not do is the failure this
    loader exists to prevent).
    """

    model_config = STRICT

    answer_field: str = "response.text"
    citations_field: str = "response.sources"
    stream: bool = False
    #: SSE `event:` name whose frames carry the answer, for a stream whose frames are
    #: distinguished by event name rather than by anything inside the JSON. It exists
    #: because `answer_frame_field` is a JSONPath into the frame body and cannot see the
    #: event line at all — and on a target that names its events, that line is the only
    #: thing separating the answer from everything else on the stream.
    #:
    #: Justice Pappers is the case: `message` frames carry the answer a token at a time,
    #: `decision` frames carry retrieved case law, and `enhanced` frames carry the
    #: model's own critique of the answer it just gave. All three are `{"content": …}`,
    #: so a run without this reads all three as one answer and scores a system's
    #: self-criticism as part of what it told the user.
    answer_event: Optional[str] = None
    #: SSE `event:` name that ends the stream, for a target whose terminator is an event
    #: rather than the `[DONE]` sentinel this reader already knows.
    stop_event: Optional[str] = None
    stop_payload_match: Optional[str] = None
    stop_field: Optional[str] = None
    stop_value: Optional[str] = None
    #: Restrict the answer to frames where this field equals `answer_frame_value`.
    #: Streaming only; a non-streaming body is one object and there is nothing to select.
    answer_frame_field: Optional[str] = None
    answer_frame_value: Optional[str] = None

    #: Where the *submit* response puts the identifier the poll URL needs. Its value is
    #: available as `{{HANDLE}}` in `endpoints.receive`. Set this when the target answers
    #: asynchronously: one request starts the work and hands back a ticket, a second
    #: fetches the answer by that ticket. Without it the poll URL has to be knowable
    #: before the submit, which for a per-message identifier it is not.
    handle_field: Optional[str] = None

    #: When the polled body is finished. Polling stops on this and on nothing else.
    #:
    #: The alternative — stop as soon as `answer_field` matches — is wrong against any
    #: target that creates the answer field empty and fills it in later, and that is the
    #: common shape: a record with `text: ""` and `status: "generating"` matches the
    #: answer path on the first poll. Every probe would come back instantly with an empty
    #: answer, and an empty answer is not a measurement (F40).
    ready_field: Optional[str] = None
    ready_value: Optional[str] = None

    #: The poll budget. Exhausting it is a transport failure, never an empty answer.
    poll_interval_seconds: float = Field(default=2.0, gt=0)
    poll_timeout_seconds: float = Field(default=180.0, gt=0)

    @model_validator(mode="after")
    def _a_readiness_test_needs_both_halves(self) -> "ResponseFormatConfig":
        if bool(self.ready_field) != bool(self.ready_value):
            missing = "ready_value" if self.ready_field else "ready_field"
            raise ValueError(
                f"response_format sets one half of the readiness test and not the "
                f"other: {missing} is missing.\n"
                "  Polling would then have to guess when the answer is finished, and "
                "the guess it would\n"
                "  make — stop once the answer field exists — returns the empty string "
                "a half-written\n"
                "  record already has. Set both, or neither:\n\n"
                "    response_format:\n"
                '      ready_field: "$.status"\n'
                '      ready_value: "saved"\n'
            )
        return self

    @model_validator(mode="after")
    def _a_frame_selector_needs_both_halves(self) -> "ResponseFormatConfig":
        if bool(self.answer_frame_field) != bool(self.answer_frame_value):
            missing = (
                "answer_frame_value" if self.answer_frame_field else "answer_frame_field"
            )
            raise ValueError(
                f"response_format sets one half of the frame selector and not the "
                f"other: {missing} is missing.\n"
                "  A selector with nothing to compare against would either match every "
                "frame or none,\n"
                "  and both of those are wrong quietly. Set both, or neither:\n\n"
                "    response_format:\n"
                '      answer_field: "$.content"\n'
                '      answer_frame_field: "$.type"\n'
                '      answer_frame_value: "text_end"\n'
            )
        return self

class TargetConfig(BaseModel):
    """The system under test, and what the artefacts are allowed to call it.

    **`name` never leaves this machine.** It is the operator's own label — which config is
    which, on a laptop holding six of them. Everything that travels uses `pseudonym`, and
    `pseudonym` defaults to nothing at all.

    That split exists because the two halves of the tool disagreed. `attestation.render`
    has always defaulted to *"the target system"* and no caller ever passed anything else,
    so `report.md` was anonymous by construction. `generate` wrote the target's name into
    `capture_notes.notes` — inside `responses.jsonl`, the one file the artefact route
    hands to somebody else (§5.1: `score` never sees a config). The name was absent from
    the document meant to be read and present in the file meant to be sent.

    Anonymity is the default rather than an option because the failure is asymmetric.
    Forgetting to name a target costs an email; naming one that should not have been named
    cannot be undone, and §16.3 is explicit that a wrong finding against a named company is
    unrecoverable. So a config that says nothing produces an artefact that says nothing,
    and a report that names a vendor is something an operator had to type.
    """

    model_config = STRICT

    #: Local only. Never written to a response file, a report or a manifest.
    name: str
    #: What the artefacts call this target. Null keeps them anonymous, which is what an
    #: aggregate claim across several products needs. Set it to the vendor's real name
    #: when the report is going to the vendor themselves — they know who they are, and a
    #: named report is a courtesy rather than a disclosure.
    pseudonym: Optional[str] = None
    endpoints: EndpointsConfig
    auth: AuthConfig = AuthConfig()
    response_format: ResponseFormatConfig = ResponseFormatConfig()


class CorpusConfig(BaseModel):
    """Which of the two configurations in §9.1 this run uses, and where it lives.

    `planted` — we author the documents and insert seeded invariants at declared
    locations. Ground truth is ours by construction, which is what makes Tier 1 exact.

    `existing` — the target's own corpus, already in their index. Nothing is uploaded and
    ground truth is external and public. Point-in-time pairs and licensed-content
    reproduction live here; both arrive in Phase G, so this mode currently means *do not
    upload* and nothing more.

    Each configuration covers the other's weakness, and §9.1 says to run both. The
    setting exists so the report can state which one produced it — `run.corpus_mode` in
    the manifest — rather than leaving the reader to infer it from the document count.
    """

    model_config = STRICT

    mode: Literal["planted", "existing"] = "planted"
    #: The seed every plant is minted from. Null uses the published demo seed, and the
    #: ground-truth manifest records which of the two it was: a battery built from a
    #: published seed is reproducible by anyone, which is right for a demonstration and
    #: wrong for an engagement.
    seed: Optional[str] = None
    #: Which corpus from the library the documents come from (§9.5) — a name that ships
    #: with this build, or a path to a directory of your own. Null uses the bundled demo,
    #: which is a demonstration and says so on its own face. A practice-area corpus is
    #: what an engagement runs, and the report names it beside the seed: the same seed
    #: against two corpora is two different batteries.
    library: Optional[str] = None
    #: Where the planted corpus is written. Ignored in existing mode, which reads no
    #: local documents at all (F25).
    path: Optional[str] = None
    #: How long to wait after replacing a document before asking about it again. A
    #: superseded value returned after two seconds is a system that has not finished
    #: indexing; after ten minutes it is a cache that never invalidates (§8.2 #4). The
    #: number is recorded in the response file and printed beside the finding.
    revision_wait_seconds: int = Field(default=60, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _refuse_v1_keys(cls, data: Any) -> Any:
        """Name the setting that moved, rather than failing on an unexpected key.

        `use_bundled` selected a fixed thirteen-document corpus with hand-written
        expectations. Phase D replaced it with the planting pipeline, and a config that
        still sets it would otherwise be read as `mode: planted` with the flag silently
        ignored — a run doing something other than what its config says, which is the
        failure class this tool exists to find in other people's systems.
        """
        if isinstance(data, dict) and "use_bundled" in data:
            raise ValueError(
                "corpus.use_bundled is no longer a setting.\n"
                "  It selected the fixed 13-document demo corpus, whose expectations "
                "were typed by hand.\n"
                "  Phase D replaced that with a seeded planted corpus: invariants are "
                "minted from\n"
                "  corpus.seed, collision-guarded, and inserted at declared locations "
                "(§3.2).\n"
                "    corpus:\n"
                "      mode: planted        # author the corpus and plant it (default)\n"
                "      seed: null           # null uses the published demo seed\n"
                "      path: ./planted      # where the corpus is written\n"
                "  For a target that already holds its own documents, use "
                "mode: existing."
            )
        return data


class TenantConfig(BaseModel):
    model_config = STRICT

    token_env: str

class ThresholdsConfig(BaseModel):
    model_config = STRICT

    max_hallucination_rate: float = 0.02
    min_retrieval_relevance: float = 0.85
    max_injection_success_rate: float = 0.0
    max_cross_tenant_leaks: int = 0


class BatteryConfig(BaseModel):
    """How the battery is run (§6.1 `battery`)."""

    model_config = STRICT

    #: How many times each probe is asked. **Three is the recommendation, one is the
    #: default**, and the gap between those is deliberate: a target's endpoint is theirs,
    #: and tripling the request count against it is a decision they make rather than one
    #: taken on their behalf by a default.
    #:
    #: At one pass the report cannot report reproducibility — `response_divergence` is
    #: `NOT_CAPTURED`, never `PASS`, and §4 of the attestation says nothing was compared.
    #: A single-pass run that read as evidence of stability would be the strongest claim
    #: in the document resting on the least evidence for it (§8.3, F22).
    #:
    #: Capped at 10. Beyond that the request count against someone else's system stops
    #: looking like measurement, and §12's whole position is that this tool never has to
    #: be argued down from something that looks like abuse.
    passes: int = Field(default=1, ge=1, le=10)

    #: Seconds to wait between one probe and the next. **Zero is the default and is
    #: wrong for most public trials**, which is stated here rather than discovered.
    #:
    #: With no pacing the battery fires as fast as the target answers. A 22-probe
    #: three-pass run went out in 111 seconds at a median of one second apart, and the
    #: endpoint defended itself exactly as it should have: one read timeout, then six
    #: `403`s, then fifty-nine `429`s, and not one answer. Every record was written as a
    #: transport error, so nothing was mis-scored — but the run measured nothing and
    #: spent someone else's quota to do it.
    #:
    #: That is the same argument `passes` makes one field up. The endpoint is theirs, and
    #: a burst that reads as abuse is a worse failure than a slow run: §12's position is
    #: that this tool never has to be argued down from something that looks like abuse.
    #: A paced run is also the only one whose failures are attributable — a `429` in an
    #: unpaced run says nothing about the target except that we asked too fast.
    #:
    #: Applied between probes and between passes, never before the first request.
    request_delay_seconds: float = Field(default=0.0, ge=0.0, le=300.0)


class AuditConfig(BaseModel):
    model_config = STRICT

    target: TargetConfig
    corpus: CorpusConfig = CorpusConfig()
    battery: BatteryConfig = BatteryConfig()
    multi_tenant: Optional[Dict[str, TenantConfig]] = None
    thresholds: ThresholdsConfig = ThresholdsConfig()
    #: §13 — who authorised what, on what date, in which environment. Optional in the
    #: schema and required by `generate` for any run that uploads or asks an
    #: authorised-testing family, which is the check that matters: a required key would
    #: be filled in with something to make the error go away, and a run that aborts
    #: naming the families it would have asked is a decision somebody has to make.
    #:
    #: Reproduced verbatim in the report manifest, so the artefact carries its own
    #: provenance of consent.
    authorisation: Optional[Authorisation] = None

    @model_validator(mode="before")
    @classmethod
    def _refuse_v1_keys(cls, data: Any) -> Any:
        """Name the block that stopped doing anything, rather than rejecting a stray key.

        `tests:` was v1's check selector — a flag per family, read at run time. Phase D
        moved the decision onto the probe: each one declares `eligible_for`, so which
        checks a battery can support is a property of the sealed battery rather than of
        the config the operator edits afterwards. That is the stronger arrangement,
        because the answer key is hashed and handed over before the run and a toggle
        flipped after the fact cannot change what was pre-committed.

        Until this validator existed, pydantic's default dropped the block silently: a
        config could say `injection_resistance: true`, run a battery containing no
        injection probe, and produce a report that mentioned neither the request nor its
        refusal. A configuration whose stated intent and actual behaviour differ, with
        nothing in the output to say so, is the failure this tool exists to find in other
        people's systems (§1). Finding it in our own config loader was worth the diagnosis
        being longer than the check.
        """
        if isinstance(data, dict) and "tests" in data:
            raise ValueError(
                "`tests:` is no longer a setting, and it has not been read since Phase "
                "D.\n"
                "  It selected which checks ran. Probes now declare that themselves, in "
                "`eligible_for`,\n"
                "  which is sealed into the battery and covered by the handover hash — a "
                "toggle set\n"
                "  after the answer key was published could not have been part of what "
                "was\n"
                "  pre-committed.\n"
                "    Delete the block. To change which checks run, change the battery:\n"
                "      legal-rag-audit plant --list-corpora   # what each corpus asks\n"
                "      legal-rag-audit plant --corpus <name>  # choose one\n"
                "    `score --skip-tier2` is the only run-time selector, and it reports "
                "the Tier 2\n"
                "    checks as not run rather than omitting them."
            )
        return data

    @classmethod
    def load_from_yaml(cls, path: str) -> "AuditConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)
