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
    model_config = STRICT

    type: str = "none" # bearer | api_key | basic | none
    token_env: Optional[str] = None

class ResponseFormatConfig(BaseModel):
    model_config = STRICT

    answer_field: str = "response.text"
    citations_field: str = "response.sources"
    stream: bool = False
    stop_payload_match: Optional[str] = None
    stop_field: Optional[str] = None
    stop_value: Optional[str] = None

class TargetConfig(BaseModel):
    model_config = STRICT

    name: str
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
