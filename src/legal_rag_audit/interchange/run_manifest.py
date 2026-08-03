"""`run_manifest.v1` — the provenance block of a report (V2_FULL_PLAN.md §6.5, F23).

Sufficient for an independent party to reproduce the run: which build scored it, over
which exact bytes, with which models at which lines, and what was committed to before
any of it happened.

One rule governs the shape, and it is the same rule as F40. **A field this build
cannot populate is present and null, with its reason in `not_recorded`.** An omitted
field and an unknown value read identically on the page, and the difference matters:
"we do not know which corpus this was" is a caveat a reader must be given, whereas a
manifest that simply has no `corpus_hash` key looks complete. `unrecorded_gaps()` is
the machine-checkable form of that rule and a test holds it.
"""

from typing import Any, Final, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .versions import RUN_MANIFEST_V1


class ToolProvenance(BaseModel):
    """Which build produced the report."""

    model_config = ConfigDict(extra="forbid")

    version: str
    commit_sha: Optional[str] = None
    #: `present` or `absent`. Whether the commit carries a signature, not whether we
    #: verified it — self-attested verification convinces nobody who is doubting us,
    #: and gpg is a network path the offline guard cannot see. See provenance/tool.py.
    commit_signature: Optional[str] = None
    #: The command a reader runs to verify the signature themselves.
    commit_signature_verify_with: Optional[str] = None
    #: `clean` or `modified`. A modified tree means the sha does not describe the
    #: code that ran, and a reproducibility claim resting on it would be false.
    working_tree: Optional[str] = None
    commit_unavailable: Optional[str] = None


class InputDigests(BaseModel):
    """The bytes this run was computed from."""

    model_config = ConfigDict(extra="forbid")

    responses_hash: Optional[str] = None
    query_set_hash: Optional[str] = None
    ground_truth_manifest_hash: Optional[str] = None
    config_hash: Optional[str] = None
    #: `score` never sees the corpus. Populated only from a handover record, and
    #: labelled as carried rather than verified when it is.
    corpus_hash: Optional[str] = None
    corpus_hash_provenance: Optional[str] = None
    #: How each digest was computed, so verification does not require this package.
    recipes: dict[str, str] = Field(default_factory=dict)


class PreCommitment(BaseModel):
    """Whether the answer key was fixed before the responses existed (§3.6)."""

    model_config = ConfigDict(extra="forbid")

    #: `verified` — a handover record was supplied and every digest matched.
    #: `absent` — none was supplied, so this run makes no pre-commitment claim.
    status: Literal["verified", "absent"]
    handover_record: Optional[str] = None
    created: Optional[str] = None
    #: Artefacts whose digests were recomputed here and matched.
    verified: list[str] = Field(default_factory=list)
    #: Artefacts recorded at handover that this run cannot check — the corpus, which
    #: `score` does not have.
    carried: list[str] = Field(default_factory=list)


class RunFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started: str
    finished: str
    passes: int
    #: The seed every plant was minted from. Null for a battery whose expectations were
    #: authored directly rather than planted — a report from one of those cannot claim
    #: its invariants were unguessable, and the null is what stops it claiming so by
    #: omission.
    seed: Optional[str] = None
    #: Where the seed came from, in words. The published demo seed and an engagement seed
    #: are both seeds; only one of them makes the battery unguessable, and a reader is
    #: entitled to know which they are holding.
    seed_source: Optional[str] = None
    #: `planted` — we authored the corpus and inserted the invariants. `existing` — the
    #: target's own documents, with external ground truth (§9.1). Each configuration
    #: covers the other's weakness, so which one produced a report changes what it can
    #: establish.
    corpus_mode: Optional[str] = None
    #: How many invariants were planted. Zero on an existing-corpus run.
    plants: int = 0
    #: False, and enforced: `score` runs inside `offline()` and
    #: scripts/check_no_remote_scoring.sh keeps the removed path out of the tree.
    remote_scoring: bool = False
    #: Whether denominators came from the probe file or were reconstructed (F39).
    eligibility_source: str


class InstrumentRecord(BaseModel):
    """One model in the scoring path, and the line it was read against."""

    model_config = ConfigDict(extra="forbid")

    check: str
    role: str
    model: str
    weights_revision: Optional[str] = None
    weights_revision_unavailable: Optional[str] = None
    library: str
    library_version: Optional[str] = None
    library_version_unavailable: Optional[str] = None
    threshold: float
    threshold_source: str
    threshold_kind: str


class ScoringFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks_registered: int
    tier2_skipped: bool
    instruments: list[InstrumentRecord] = Field(default_factory=list)
    #: Digest of the report with this manifest removed — the findings themselves.
    #: NF2 says the same inputs produce byte-identical findings; this is that claim
    #: reduced to one string a reader can compare between two runs. The manifest is
    #: excluded because it records when the run happened, which cannot be identical
    #: and should not be.
    findings_hash: str
    findings_hash_recipe: str


class BatteryComposition(BaseModel):
    """What was asked, declared before the run (§3.5, F39)."""

    model_config = ConfigDict(extra="forbid")

    total_probes: int
    #: A probe with no correct answer scores the opposite way round: answering is the
    #: finding and refusing is the pass. The split belongs on the page because a
    #: reader cannot otherwise tell what the denominators are made of.
    positive_probes: int
    no_correct_answer_probes: int
    eligible_by_check: dict[str, int] = Field(default_factory=dict)


class CaptureSummary(BaseModel):
    """What the response file did not carry, and which checks that disabled."""

    model_config = ConfigDict(extra="forbid")

    records: int
    transport_errors: int
    citations_captured: bool
    retrieved_chunks_captured: bool
    document_ids_supplied: bool
    #: Records whose `query` was exactly the probe text the handover sealed.
    #:
    #: The other end of the pre-commitment. Hashing the probe file fixes *which questions
    #: were to be asked*; this is the count that were. It matters most on the artefact
    #: route (§5.1.1), where the response file comes from the target's own harness and
    #: this is the only mechanical link between the sealed battery and the answers.
    probes_asked_verbatim: int = 0
    #: Probes whose question arrived wrapped in something longer — a system preamble, a
    #: formatting instruction. The answer still answers our question, so the finding
    #: stands; what does not stand is the claim that it was asked verbatim, and naming
    #: them is what stops a reader assuming otherwise.
    probes_asked_wrapped: list[str] = Field(default_factory=list)
    #: Checks that did not run, and the reason each one gives.
    checks_not_run: dict[str, str] = Field(default_factory=dict)
    #: Verbatim from the response file's capture_notes, if it carried any.
    notes: Optional[str] = None


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["run_manifest.v1"] = Field(
        default=RUN_MANIFEST_V1, alias="schema"
    )
    tool: ToolProvenance
    inputs: InputDigests
    pre_commitment: PreCommitment
    run: RunFacts
    scoring: ScoringFacts
    battery: BatteryComposition
    capture: CaptureSummary
    #: §13 verbatim. Null until the authorisation gate lands in Phase I; recorded as
    #: a gap rather than left out, because a report on an authorised-testing battery
    #: has to carry its own provenance of consent.
    authorisation: Optional[dict[str, Any]] = None
    #: Every field above that is null, mapped to why. See `unrecorded_gaps`.
    not_recorded: dict[str, str] = Field(default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


#: The §6.5 checklist, as dotted paths into the document. Every one of these is either
#: populated or explained; `unrecorded_gaps` is what makes that testable rather than
#: a habit that erodes the first time a field is inconvenient.
REQUIRED_BY_SECTION_6_5: Final[tuple[str, ...]] = (
    "inputs.corpus_hash",
    "inputs.query_set_hash",
    "inputs.ground_truth_manifest_hash",
    "inputs.config_hash",
    "inputs.responses_hash",
    "tool.version",
    "tool.commit_sha",
    "scoring.instruments",
    "run.passes",
    "run.seed",
    "run.started",
    "run.finished",
    "run.corpus_mode",
    "run.remote_scoring",
    "authorisation",
    "battery",
    "capture",
)


def _at(document: dict[str, Any], path: str) -> Any:
    node: Any = document
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def unrecorded_gaps(document: dict[str, Any]) -> list[str]:
    """§6.5 fields that are neither populated nor explained in `not_recorded`.

    A non-empty result is a defect in the manifest, not in the run: it means the
    report carries a silent hole where a reader would read completeness.
    """
    explained = document.get("not_recorded") or {}
    gaps = []
    for path in REQUIRED_BY_SECTION_6_5:
        value = _at(document, path)
        empty = value is None or (isinstance(value, (list, dict)) and not value)
        if empty and path not in explained:
            gaps.append(path)
    return gaps
