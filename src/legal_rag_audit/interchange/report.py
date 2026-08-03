"""`report.v2` — the report body (V2_FULL_PLAN.md §6.6).

The JSON is the evidence; `report.md` is the testimony. This is the contract for the
JSON, so a consumer — their engineer, their buyer's diligence team, a tool nobody has
written yet — can build against it without reading our source.

**Two deviations from the §6.6 sketch, both deliberate.**

*The version number tracks the tool generation, not the schema's.* Every other
contract here is `name.v1`; this one is `report.v2` because that is what §6.6 and the
plan's file name say, and the artefact is already discussed under that name. The rule
from here is the same as everywhere else: a breaking change makes `report.v3`, and
`report.v2` means one thing forever.

*Checks are keyed by name, not nested under `tier1` / `tier2`.* The sketch nests them.
Nesting makes a check's address depend on its tier — and the tier does change. Phase D
moved `abstention` from Tier 2 to Tier 1 by rewriting it as an inverted check, which is
exactly the event that would have broken every consumer's path to it under the nested
shape. A consumer's address for a check must not move because we improved how it is
scored. So `checks` is flat and addressable, and `tier1` / `tier2` are ordered *lists of
names* carrying §10.1's reading order.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .run_manifest import RunManifest
from .versions import REPORT_V2


class CheckResult(BaseModel):
    """What one registered check concluded, or why it did not conclude anything."""

    model_config = ConfigDict(extra="forbid")

    check: str
    tier: int
    #: §3.6.1 — whether this check's expectation was published with the battery or
    #: sealed until this report. On the page because a reader is entitled to know
    #: which half of the battery the target could see in advance.
    key: str
    #: One line: how the check decides. Printed beside the result so the reader is not
    #: taking the verdict on trust.
    recipe: str
    #: What this check does **not** establish, in the same artefact as the finding
    #: rather than in a later post (§3.3). Mandatory where §8.2 names one — injection
    #: measures instruction-boundary override, not exfiltration capability — and the
    #: field exists so a report cannot print that finding without the sentence.
    limit: Optional[str] = None
    #: A measurement rather than a finding (§8.2 #15). It has no pass condition, so it
    #: never appears in the findings table and its verdict is not a verdict.
    measurement: bool = False
    #: Probes declared eligible before the run. The denominator (F39).
    eligible: int
    scored: int
    not_captured: int
    failed: int
    #: `PASS` · `FAIL` · `NOT_ELIGIBLE` · `NOT_CAPTURED`. The last two exist so an
    #: absent check never reads as a passing one (F40).
    status: Literal["PASS", "FAIL", "NOT_ELIGIBLE", "NOT_CAPTURED"]
    #: Why the check did not run. Present exactly when it did not.
    reason: Optional[str] = None
    #: Named when *part* of the check could not run, so a partial result never reads
    #: as a complete one.
    partial: Optional[str] = None
    #: The evaluator's own output. Still open, because each check reports different
    #: facts about its own recipe and a schema that flattened them would be wrong about
    #: the one field carrying the evidence. Phase D narrowed the part that matters: every
    #: Tier 1 evaluator now names what it saw under `appeared` and `absent`, so the
    #: evidence bundle reads two keys rather than guessing at nine.
    detail: dict[str, Any] = Field(default_factory=dict)
    #: Tier 2 only (F24). The numbers behind the verdict, bucketed, with the
    #: configured line marked — because a bare PASS/FAIL hides how close to the line
    #: every record sat, and hides that the line is a setting of ours.
    distribution: Optional[dict[str, Any]] = None


class Summary(BaseModel):
    """Counts, never a rate (§3.5, Appendix D)."""

    model_config = ConfigDict(extra="forbid")

    checks_registered: int
    passed: int
    failed: int
    not_eligible: int
    not_captured: int
    #: How much of the battery was published in advance (§3.6.1), so the withholding
    #: is a countable fact rather than an atmosphere.
    published_keys: int
    withheld_keys: int
    #: Checks with no pass condition. Named rather than folded into `passed`, where
    #: they would inflate the count of things that could have failed and did not.
    measurements: list[str] = Field(default_factory=list)
    tier1_findings: list[str] = Field(default_factory=list)
    tier2_findings: list[str] = Field(default_factory=list)
    verdict: Literal["PASS", "FAIL"]


class Capture(BaseModel):
    """What the response file carried, which decides what could be checked at all."""

    model_config = ConfigDict(extra="forbid")

    eligibility_source: str
    #: Three states, not two. `null` means *the response file does not say* — a file
    #: where every record happens to carry `null` citations is indistinguishable from
    #: one whose producer never looked, and the report must not claim to know which.
    citations_captured: Optional[bool] = None
    retrieved_chunks_captured: Optional[bool] = None
    document_ids_supplied: bool
    passes: int
    records: int
    transport_errors: int


class EvidenceIndex(BaseModel):
    """Where the verbatim material for one check's findings was written (F41)."""

    model_config = ConfigDict(extra="forbid")

    file: str
    instances: int


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["report.v2"] = Field(default=REPORT_V2, alias="schema")
    manifest: RunManifest
    #: Check names in reading order (§10.1): deal-enders first, mechanism last.
    tier1: list[str] = Field(default_factory=list)
    tier2: list[str] = Field(default_factory=list)
    checks: dict[str, CheckResult]
    summary: Summary
    capture: Capture
    #: check name -> where its verbatim evidence was written. Only present for checks
    #: with Tier 1 findings, and only when an output directory was given.
    evidence: dict[str, EvidenceIndex] = Field(default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


#: Fields of a report that are not findings. `findings_hash` covers everything else,
#: and `score.findings_of` drops exactly these — the two must agree or the digest is
#: one nobody can recompute from the document they were given.
NOT_FINDINGS = ("schema", "manifest")


def build_findings(
    *,
    tier1: list[str],
    tier2: list[str],
    checks: dict[str, Any],
    summary: dict[str, Any],
    capture: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """The canonical findings document, validated and serialised.

    Built *before* the manifest, because the manifest records this document's digest
    and a reader has to be able to recompute it. Hashing the raw dicts instead would
    produce a digest over a shape that never appears in the file — the models fill in
    absent optional fields as nulls, so the two differ in every check that ran
    cleanly, and the published recipe would be a false instruction.
    """
    document = {
        "tier1": tier1,
        "tier2": tier2,
        "checks": {
            name: CheckResult(**value).model_dump(mode="json")
            for name, value in checks.items()
        },
        "summary": Summary(**summary).model_dump(mode="json"),
        "capture": Capture(**capture).model_dump(mode="json"),
        "evidence": {
            name: EvidenceIndex(**value).model_dump(mode="json")
            for name, value in evidence.items()
        },
    }
    return document
