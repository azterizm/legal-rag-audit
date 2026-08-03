#!/usr/bin/env python3
"""Validate sbom/*.cdx.json against the published CycloneDX 1.6 schema.

`scripts/gen_sbom.py` writes those files by hand, from the lockfiles, for reasons its
docstring gives. That leaves one gap: "this is a CycloneDX document" would otherwise be
a claim checked only against our own reading of the specification. This runs the
schema published by the CycloneDX project, via `cyclonedx-python-lib`, so something
other than us says the output is well formed.

Not part of the default gate set, because it needs the `audit` layer — a hundred
packages a contributor has no other reason to install. CI runs it on every push and the
run is public, which is the form of verification that is worth anything to a stranger
anyway (§12.6).

    python3 -m pip install --require-hashes -r requirements/audit.txt
    python3 scripts/validate_sbom.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SBOM_DIR = REPO_ROOT / "sbom"


def main() -> int:
    try:
        from cyclonedx.schema import SchemaVersion
        from cyclonedx.validation.json import JsonStrictValidator
    except ImportError:
        print(
            "cyclonedx-python-lib is not installed. This check runs against the "
            "audit layer:\n"
            "    python3 -m pip install --require-hashes -r requirements/audit.txt",
            file=sys.stderr,
        )
        return 2

    documents = sorted(SBOM_DIR.glob("*.cdx.json"))
    if not documents:
        print(f"FAIL: no SBOMs in {SBOM_DIR}. Run scripts/gen_sbom.py.")
        return 1

    validator = JsonStrictValidator(SchemaVersion.V1_6)
    failures = []

    for document in documents:
        error = validator.validate_str(document.read_text(encoding="utf-8"))
        if error is None:
            print(f"  {document.relative_to(REPO_ROOT)}: valid CycloneDX 1.6")
        else:
            failures.append(f"{document.relative_to(REPO_ROOT)}: {error}")

    if failures:
        print("\nFAIL: not valid CycloneDX 1.6:")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"\n  clean ({len(documents)} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
