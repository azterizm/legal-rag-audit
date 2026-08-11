#!/usr/bin/env python3
"""Generate a CycloneDX 1.6 SBOM per dependency layer, from the lockfiles.

An SBOM is the artefact a procurement team already knows how to consume (§12.4). This
one is generated from `requirements/*.txt` rather than from an installed environment,
and the difference is the point: an environment SBOM describes whatever happened to be
on the machine that ran the scanner, while the lockfile is the thing the repository
commits to. The hashes below are the lockfile's own — the same bytes `--require-hashes`
enforces at install time — so the SBOM and the installer are making one claim, not two.

**One SBOM per layer, not one for the project.** The whole security story is that a
target installs `generate` and nothing else (§5.3, F31). A single merged SBOM listing
torch would misdescribe what lands on their machine, which is the only question they
are asking.

**Deterministic, so drift is checkable.** CycloneDX permits `metadata.timestamp` and a
random `serialNumber`; both would change on every generation and make a committed SBOM
impossible to verify against the lockfile it claims to describe. The serial number here
is a UUIDv5 over the lockfile's SHA-256, and the timestamp is omitted with its reason
recorded in `metadata.properties` — an absent field and an unknown value read
identically, and the reader is entitled to know which one they have (the F40 rule,
applied to provenance).

**The graph is real.** uv writes `# via <package>` under each requirement, so the
`dependencies` array carries the actual resolution graph rather than a flat list of
everything hanging off the root. A reader can see that `torch` arrives through
`sentence-transformers` and not because we asked for it.

**What is not in here: licences.** A lockfile carries no licence metadata, and reading
it off installed distributions would make the output depend on a machine again. The gap
is recorded in `metadata.properties` rather than left for a procurement reviewer to
notice as an absence.

    python3 scripts/gen_sbom.py            # write
    python3 scripts/gen_sbom.py --check    # verify, exit 1 on drift
"""

import argparse
import hashlib
import json
import re
import sys
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_DIR = REPO_ROOT / "requirements"
OUT_DIR = REPO_ROOT / "sbom"

LAYERS = ("generate", "score", "dev", "audit")

SPEC_VERSION = "1.6"
SCHEMA_URL = "http://cyclonedx.org/schema/bom-1.6.schema.json"

#: Namespace for the deterministic serial numbers. Any fixed UUID would do; this is the
#: standard URL namespace, so the derivation is one a stranger can repeat with the
#: standard library and no reference to this file.
SERIAL_NAMESPACE = uuid.NAMESPACE_URL
PROJECT_URL = "https://github.com/azterizm/legal-rag-audit"

REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.\-]+)\s*==\s*(?P<version>[^\s;\\]+)"
    r"(?:\s*;\s*(?P<marker>[^\\]+?))?\s*(?:\\)?$"
)
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
VIA_INLINE_RE = re.compile(r"^#\s*via\s+(.+)$")
VIA_CONTINUATION_RE = re.compile(r"^#\s{2,}(\S.*)$")


def normalise(name: str) -> str:
    """PEP 503 name normalisation, so `via` comments resolve against requirements."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Entry:
    """One pinned requirement, as the lockfile states it."""

    name: str
    version: str
    #: The environment marker, verbatim. Present on packages that install on some
    #: platforms and not others — `numpy` resolves to two versions across the supported
    #: interpreters, and a component that is conditional is a different statement from
    #: one that always installs.
    marker: str
    #: SHA-256 of each distribution file (wheels per platform, plus the sdist). Several
    #: per package is normal; see the note written into every component.
    hashes: tuple[str, ...]
    #: What pulled it in. A `-r requirements/*.in` entry means we asked for it directly.
    via: tuple[str, ...]

    @property
    def purl(self) -> str:
        return f"pkg:pypi/{normalise(self.name)}@{self.version}"

    @property
    def ref(self) -> str:
        # The marker is part of the identity: two `numpy` entries share a name and
        # differ only by which interpreter selects them, and a bom-ref must be unique.
        if self.marker:
            return f"{self.purl}?marker={self.marker}"
        return self.purl

    @property
    def direct(self) -> bool:
        return any(v.startswith("-r ") for v in self.via)


def parse_lockfile(path: Path) -> list[Entry]:
    """Read a uv-generated lockfile into entries, including the `# via` graph."""
    entries: list[Entry] = []
    name = version = marker = None
    hashes: list[str] = []
    via: list[str] = []
    in_via = False

    def flush() -> None:
        nonlocal name, version, marker, hashes, via, in_via
        if name is not None:
            entries.append(
                Entry(
                    name=name,
                    version=version,
                    marker=marker or "",
                    hashes=tuple(sorted(set(hashes))),
                    via=tuple(via),
                )
            )
        name = version = marker = None
        hashes, via, in_via = [], [], False

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue

        match = REQUIREMENT_RE.match(line)
        if match and not raw.startswith((" ", "\t", "#")):
            flush()
            name = match.group("name")
            version = match.group("version")
            marker = (match.group("marker") or "").strip()
            continue

        if name is None:
            continue

        hashes.extend(HASH_RE.findall(line))

        inline = VIA_INLINE_RE.match(line)
        if inline:
            via.append(inline.group(1).strip())
            in_via = True
            continue
        if line == "# via":
            in_via = True
            continue
        if in_via:
            continuation = VIA_CONTINUATION_RE.match(line)
            if continuation:
                via.append(continuation.group(1).strip())
                continue
            in_via = False

    flush()
    return entries


def _component(entry: Entry) -> dict:
    properties = [
        {
            "name": "legal-rag-audit:hash-scope",
            "value": (
                "each hash is one distribution file (a platform wheel or the sdist), "
                "not one hash of one artefact — this is what --require-hashes verifies"
            ),
        }
    ]
    if entry.marker:
        properties.append(
            {"name": "legal-rag-audit:environment-marker", "value": entry.marker}
        )
    properties.append(
        {
            "name": "legal-rag-audit:direct",
            "value": "true" if entry.direct else "false",
        }
    )

    return {
        "type": "library",
        "bom-ref": entry.ref,
        "name": normalise(entry.name),
        "version": entry.version,
        "purl": entry.purl,
        "hashes": [{"alg": "SHA-256", "content": h} for h in entry.hashes],
        "externalReferences": [
            {
                "type": "distribution",
                "url": f"https://pypi.org/simple/{normalise(entry.name)}/",
            }
        ],
        "properties": properties,
    }


def _dependencies(entries: list[Entry], root_ref: str) -> list[dict]:
    """The resolution graph, from uv's `# via` comments.

    `via` records who required a package, so the edges are read backwards: an entry
    naming `pydantic` in its `via` block is a thing pydantic depends on.
    """
    by_name: dict[str, list[str]] = {}
    for entry in entries:
        by_name.setdefault(normalise(entry.name), []).append(entry.ref)

    edges: dict[str, set[str]] = {entry.ref: set() for entry in entries}
    edges[root_ref] = set()

    for entry in entries:
        for parent in entry.via:
            if parent.startswith("-r "):
                edges[root_ref].add(entry.ref)
                continue
            for parent_ref in by_name.get(normalise(parent), []):
                edges[parent_ref].add(entry.ref)

    # `dependsOn: []` is emitted rather than omitted: the spec distinguishes a component
    # with no dependencies from one whose dependencies were never determined, and this
    # generator knows the difference for every entry.
    return [
        {"ref": ref, "dependsOn": sorted(targets)}
        for ref, targets in sorted(edges.items())
    ]


def build(layer: str, project_version: str) -> dict:
    path = REQUIREMENTS_DIR / f"{layer}.txt"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    entries = sorted(
        parse_lockfile(path), key=lambda e: (normalise(e.name), e.version, e.marker)
    )
    if not entries:
        raise SystemExit(f"{path}: no pinned requirements found")

    root_ref = f"pkg:pypi/legal-rag-audit@{project_version}"
    serial = uuid.uuid5(SERIAL_NAMESPACE, f"{PROJECT_URL}/sbom/{layer}#{digest}")

    return {
        "$schema": SCHEMA_URL,
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": "legal-rag-audit",
                "version": project_version,
                "description": (
                    f"Endpoint-based evaluation harness for legal RAG systems — "
                    f"'{layer}' dependency layer"
                ),
                "purl": root_ref,
                "externalReferences": [
                    {"type": "vcs", "url": PROJECT_URL},
                    {"type": "website", "url": PROJECT_URL},
                ],
            },
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "gen_sbom.py",
                        "version": project_version,
                        "description": (
                            "generates this document from requirements/*.txt; see "
                            "scripts/gen_sbom.py"
                        ),
                    }
                ]
            },
            "properties": [
                {"name": "legal-rag-audit:layer", "value": layer},
                {
                    "name": "legal-rag-audit:lockfile",
                    "value": f"requirements/{layer}.txt",
                },
                {"name": "legal-rag-audit:lockfile-sha256", "value": digest},
                {
                    "name": "legal-rag-audit:serial-number-derivation",
                    "value": (
                        "uuid5(NAMESPACE_URL, "
                        f"'{PROJECT_URL}/sbom/{layer}#<sha256 of the lockfile>') — "
                        "derived rather than random so this document can be "
                        "regenerated byte-for-byte and checked against the lockfile "
                        "it describes"
                    ),
                },
                {
                    "name": "legal-rag-audit:timestamp-omitted",
                    "value": (
                        "metadata.timestamp is deliberately absent: a generation time "
                        "would change on every run and make drift undetectable. The "
                        "build time of a released artefact is recorded in its SLSA "
                        "provenance attestation instead"
                    ),
                },
                {
                    "name": "legal-rag-audit:licences-not-recorded",
                    "value": (
                        "component licences are not listed. A lockfile carries no "
                        "licence metadata, and reading it from installed "
                        "distributions would make this document depend on the "
                        "machine that generated it. Stated rather than silently "
                        "omitted"
                    ),
                },
            ],
        },
        "components": [_component(entry) for entry in entries],
        "dependencies": _dependencies(entries, root_ref),
    }


def render(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed SBOMs match the lockfiles; exit 1 on drift",
    )
    args = parser.parse_args()

    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    project_version = pyproject["project"]["version"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    drift: list[str] = []

    for layer in LAYERS:
        path = OUT_DIR / f"legal-rag-audit-{layer}.cdx.json"
        rendered = render(build(layer, project_version))

        if args.check:
            if not path.exists():
                drift.append(f"{path.relative_to(REPO_ROOT)}: missing")
            elif path.read_text(encoding="utf-8") != rendered:
                drift.append(
                    f"{path.relative_to(REPO_ROOT)}: does not match "
                    f"requirements/{layer}.txt"
                )
        else:
            path.write_text(rendered, encoding="utf-8")
            components = len(json.loads(rendered)["components"])
            print(f"  {path.relative_to(REPO_ROOT)} ({components} components)")

    if args.check:
        if drift:
            print("FAIL: the SBOMs no longer describe the lockfiles:")
            for item in drift:
                print(f"  {item}")
            print("\nRun: python3 scripts/gen_sbom.py")
            return 1
        print(f"  clean ({len(LAYERS)} SBOMs match their lockfiles)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
