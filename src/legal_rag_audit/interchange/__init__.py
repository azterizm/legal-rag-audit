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
    Plant,
    load_ground_truth,
    write_ground_truth,
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
from .schema_files import available_schemas, read_schema_document
from .versions import (
    GROUND_TRUTH_V1,
    PROBES_V1,
    RESPONSES_V1,
    SUPPORTED,
    SchemaVersionError,
    assert_schema,
)

__all__ = [
    "Adjacency",
    "CaptureNotes",
    "Expectation",
    "GROUND_TRUTH_V1",
    "GroundTruth",
    "InterchangeError",
    "PROBES_V1",
    "Plant",
    "Probe",
    "RESPONSES_V1",
    "Response",
    "ResponseFile",
    "RetrievedChunk",
    "SUPPORTED",
    "SchemaVersionError",
    "assert_schema",
    "available_schemas",
    "load_ground_truth",
    "load_probes",
    "load_responses",
    "read_records",
    "read_schema_document",
    "write_ground_truth",
    "write_probes",
    "write_records",
    "write_responses",
]
