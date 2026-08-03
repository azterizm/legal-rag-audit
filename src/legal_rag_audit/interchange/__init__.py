"""Interchange records shared by `generate` and `score`.

Pure pydantic. No transport, no ML, no filesystem beyond reading and writing the files
themselves — this package sits on both sides of the §5.1 boundary, so anything it
imports is imported by both modes.

The published JSON Schemas in `jsonschema/` are generated from these models by
`scripts/gen_schemas.py`; `tests/test_interchange.py` fails if they drift. The models
are the implementation, the schemas are the contract a third party validates against,
and there is one source of truth rather than two documents to keep in step.
"""

from .ground_truth import (
    Adjacency,
    Expectation,
    GroundTruth,
    Pairing,
    Plant,
    PlantGuard,
    SideEffect,
    load_ground_truth,
    write_ground_truth,
)
from .handover import (
    Handover,
    HashedArtefact,
    load_handover,
    now_utc,
    write_handover,
)
from .jsonl import InterchangeError, read_records, write_records
from .probe import Probe, load_probes, write_probes
from .response import (
    CaptureNotes,
    Response,
    ResponseFile,
    RetrievedChunk,
    load_responses,
    write_responses,
)
from .report import (
    NOT_FINDINGS,
    Capture,
    CheckResult,
    EvidenceIndex,
    Report,
    Summary,
    build_findings,
)
from .run_manifest import (
    BatteryComposition,
    CaptureSummary,
    InputDigests,
    InstrumentRecord,
    PreCommitment,
    RunFacts,
    RunManifest,
    ScoringFacts,
    ToolProvenance,
    unrecorded_gaps,
)
from .schema_files import available_schemas, read_schema_document
from .versions import (
    GROUND_TRUTH_V2,
    HANDOVER_V1,
    PROBES_V2,
    REPORT_V2,
    RESPONSES_V2,
    RUN_MANIFEST_V1,
    SUPPORTED,
    SchemaVersionError,
    assert_schema,
)

__all__ = [
    "Adjacency",
    "BatteryComposition",
    "Capture",
    "CaptureNotes",
    "CaptureSummary",
    "CheckResult",
    "EvidenceIndex",
    "Expectation",
    "GROUND_TRUTH_V2",
    "GroundTruth",
    "HANDOVER_V1",
    "Handover",
    "HashedArtefact",
    "InputDigests",
    "InstrumentRecord",
    "InterchangeError",
    "NOT_FINDINGS",
    "PROBES_V2",
    "Pairing",
    "Plant",
    "PlantGuard",
    "PreCommitment",
    "Probe",
    "REPORT_V2",
    "RESPONSES_V2",
    "RUN_MANIFEST_V1",
    "Report",
    "Response",
    "ResponseFile",
    "RetrievedChunk",
    "RunFacts",
    "RunManifest",
    "SUPPORTED",
    "SchemaVersionError",
    "SideEffect",
    "ScoringFacts",
    "Summary",
    "ToolProvenance",
    "assert_schema",
    "available_schemas",
    "build_findings",
    "load_ground_truth",
    "load_handover",
    "load_probes",
    "load_responses",
    "now_utc",
    "read_records",
    "read_schema_document",
    "unrecorded_gaps",
    "write_ground_truth",
    "write_handover",
    "write_probes",
    "write_records",
    "write_responses",
]
