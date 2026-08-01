"""Access to the published JSON Schema documents.

They ship inside the package rather than only at the repository root because
`legal-rag-audit schema --print responses.v1` has to work from an installed wheel —
a target implementing the format should not need to clone anything (F35).
"""

from importlib import resources
from typing import Any

import json

from .versions import SUPPORTED, SchemaVersionError

_DIR = "jsonschema"


def _filename(version: str) -> str:
    return f"{version}.schema.json"


def available_schemas() -> list[str]:
    return sorted(SUPPORTED)


def read_schema_document(version: str) -> dict[str, Any]:
    """Return the JSON Schema for a version, or refuse if it is not one we publish."""
    if version not in SUPPORTED:
        raise SchemaVersionError(
            f"No published schema for {version!r}.\n"
            f"  This build publishes: {', '.join(available_schemas())}."
        )
    files = resources.files(f"{__package__}.{_DIR}")
    return json.loads((files / _filename(version)).read_text(encoding="utf-8"))
