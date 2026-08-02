#!/usr/bin/env python3
"""Generate the published JSON Schemas from the pydantic models.

The models are the implementation; the schemas are the contract a third party
validates their own `responses.jsonl` against (F35). Hand-maintaining both guarantees
they drift, and a published contract that no longer matches what `score` accepts is
worse than none — it sends someone away to build against a spec we will reject.

So: one source of truth, generated. `tests/test_interchange.py` fails if the committed
files differ from what the models emit, the same ratchet `scripts/check_pins.py`
applies to the lockfiles.

    python3 scripts/gen_schemas.py            # write
    python3 scripts/gen_schemas.py --check    # verify, exit 1 on drift
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from legal_rag_audit.interchange.ground_truth import GroundTruth  # noqa: E402
from legal_rag_audit.interchange.handover import Handover  # noqa: E402
from legal_rag_audit.interchange.probe import Probe  # noqa: E402
from legal_rag_audit.interchange.response import (  # noqa: E402
    CaptureNotes,
    Response,
)
from legal_rag_audit.interchange.run_manifest import RunManifest  # noqa: E402
from legal_rag_audit.interchange.versions import (  # noqa: E402
    GROUND_TRUTH_V1,
    HANDOVER_V1,
    PROBES_V1,
    RESPONSES_V1,
    RUN_MANIFEST_V1,
)

OUT_DIR = REPO_ROOT / "src" / "legal_rag_audit" / "interchange" / "jsonschema"

VERSIONS = (
    PROBES_V1,
    RESPONSES_V1,
    GROUND_TRUTH_V1,
    HANDOVER_V1,
    RUN_MANIFEST_V1,
)

TITLES = {
    PROBES_V1: "Probe file (JSONL) — one probe per line",
    RESPONSES_V1: "Response file (JSONL) — one record per line",
    GROUND_TRUTH_V1: "Ground-truth manifest (JSON) — withheld, hashed at handover",
    HANDOVER_V1: "Handover record (JSON) — the pre-commitment, published before the run",
    RUN_MANIFEST_V1: "Run manifest (JSON) — the provenance block of a report",
}


def require_schema_field(node: dict) -> dict:
    """Make the `schema` declaration required in the published contract.

    The models default it, which is convenient in Python and wrong in a file: a record
    that does not say which contract it was written against is refused by the loaders
    (`assert_schema`, NF10). The JSON Schema describes the *file*, so it states the
    same requirement the loader enforces. The constructor's leniency is not part of
    the published contract and does not belong in it.
    """
    required = node.setdefault("required", [])
    if "schema" not in required:
        required.insert(0, "schema")
    return node


def build(version: str) -> dict:
    if version == PROBES_V1:
        schema = require_schema_field(Probe.model_json_schema(by_alias=True))
    elif version == RESPONSES_V1:
        # A response file holds two record shapes: an optional capture_notes header and
        # the responses themselves. The schema validates one *line*, so it is the union.
        response = require_schema_field(Response.model_json_schema(by_alias=True))
        notes = require_schema_field(CaptureNotes.model_json_schema(by_alias=True))
        defs = {}
        defs.update(response.pop("$defs", {}))
        defs.update(notes.pop("$defs", {}))
        schema = {
            "oneOf": [response, notes],
            "$defs": defs,
        }
    elif version == GROUND_TRUTH_V1:
        schema = require_schema_field(GroundTruth.model_json_schema(by_alias=True))
    elif version == HANDOVER_V1:
        schema = require_schema_field(Handover.model_json_schema(by_alias=True))
    elif version == RUN_MANIFEST_V1:
        schema = require_schema_field(RunManifest.model_json_schema(by_alias=True))
    else:
        raise SystemExit(f"unknown version {version!r}")

    return {
        **schema,
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/legal-rag-audit/schemas/{version}.schema.json",
        "title": TITLES[version],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed files match the models; write nothing",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    drift = []

    for version in VERSIONS:
        path = OUT_DIR / f"{version}.schema.json"
        rendered = json.dumps(build(version), indent=2, sort_keys=True) + "\n"

        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != rendered:
                drift.append(path.relative_to(REPO_ROOT))
        else:
            path.write_text(rendered, encoding="utf-8")
            print(f"  wrote {path.relative_to(REPO_ROOT)}")

    if drift:
        print("FAIL: published schemas do not match the models:")
        for p in drift:
            print(f"  {p}")
        print("\n  Regenerate with: python3 scripts/gen_schemas.py")
        return 1

    print("  clean" if args.check else f"  {len(VERSIONS)} schemas generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
