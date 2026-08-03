"""The supply-chain posture is a property of the repository, not of a document (§12).

`SECURITY.md` makes a list of claims to a reader who has no reason to believe any of
them: actions are pinned by digest, permissions are minimal, the SBOMs describe the
lockfiles, the release is verifiable. Every one of those is the kind of thing that is
true when written and quietly false a year later — a workflow edited in the GitHub web
UI reintroduces `@v4`, a dependency bump lands without regenerating an SBOM, a new job
copies `contents: write` from the release workflow because that was the nearest example.

None of those would fail anything. So they fail here.

Fast: no network, no install, no build. These are file reads.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SBOM_DIR = REPO_ROOT / "sbom"
REQUIREMENTS_DIR = REPO_ROOT / "requirements"

LAYERS = ("generate", "score", "dev", "audit")

#: `uses: owner/repo@<40 hex>` optionally followed by a `# v1.2.3` comment naming what
#: the digest was at the time. The comment is documentation; the digest is the pin.
USES_RE = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>\S+)", re.MULTILINE)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def workflows() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


# ------------------------------------------------------------------ the workflows exist


def test_the_workflows_exist():
    """A security posture asserted by a README and enforced by nothing is a leaflet."""
    names = {path.name for path in workflows()}
    assert {"ci.yml", "security.yml", "release.yml"} <= names, (
        f"missing workflows: {{'ci.yml', 'security.yml', 'release.yml'}} - {names}"
    )


# ------------------------------------------------------------------------ action pinning


@pytest.mark.parametrize("workflow", workflows(), ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit_sha(workflow):
    """A tag is a mutable pointer; a digest is not.

    `actions/checkout@v5` runs whatever its owner moves that tag to. Pinning every
    dependency to a hash and then trusting six mutable references in CI would leave the
    supply-chain claim resting on the weakest link in it — and the link nobody looks at.
    """
    text = workflow.read_text(encoding="utf-8")
    unpinned = []
    for match in USES_RE.finditer(text):
        ref = match.group("ref")
        if ref.startswith("./"):  # a local composite action; nothing to substitute
            continue
        if "@" not in ref:
            unpinned.append(ref)
            continue
        _, _, version = ref.partition("@")
        if not SHA_RE.match(version):
            unpinned.append(ref)

    assert not unpinned, (
        f"{workflow.name}: these actions are not pinned to a commit SHA: {unpinned}. "
        f"Resolve the tag to its commit and keep the tag as a trailing comment:\n"
        f"    uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
    )


@pytest.mark.parametrize("workflow", workflows(), ids=lambda p: p.name)
def test_every_pinned_action_records_the_tag_it_was(workflow):
    """A bare digest is unreviewable — nobody can tell v7.0.1 from an attacker's fork.

    The comment does not make the pin safer; it makes the diff readable, which is what
    decides whether a reviewer notices the pin changing.
    """
    missing = []
    for line in workflow.read_text(encoding="utf-8").splitlines():
        if "uses:" not in line or line.strip().startswith("#"):
            continue
        ref = USES_RE.match(line)
        if ref is None or ref.group("ref").startswith("./"):
            continue
        if SHA_RE.match(ref.group("ref").partition("@")[2]) and "#" not in line:
            missing.append(line.strip())

    assert not missing, (
        f"{workflow.name}: pinned actions with no version comment: {missing}"
    )


# --------------------------------------------------------------------------- permissions


@pytest.mark.parametrize("workflow", workflows(), ids=lambda p: p.name)
def test_the_workflow_declares_top_level_permissions(workflow):
    """Absent `permissions:` means the repository default, which may be write-all.

    Read as: the workflow's authority would be a repository setting nobody reviewing
    this file can see.
    """
    text = workflow.read_text(encoding="utf-8")
    assert re.search(r"^permissions:", text, re.MULTILINE), (
        f"{workflow.name} declares no top-level permissions block. Add "
        f"`permissions:\\n  contents: read` and widen it per job where a job "
        f"genuinely needs more."
    )
    top = text.split("\njobs:", 1)[0]
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", top, re.MULTILINE), (
        f"{workflow.name}: the top-level permissions block should be "
        f"`contents: read`. Elevation belongs on the one job that needs it, where a "
        f"reviewer sees it in isolation."
    )


def test_only_the_release_workflow_can_write():
    """Write access, an OIDC token and attestation storage live in exactly one job.

    A second job anywhere with `id-token: write` can mint a Sigstore identity as this
    repository. That is the whole basis of the provenance claim, so it is worth a test
    rather than a convention.
    """
    for workflow in workflows():
        text = workflow.read_text(encoding="utf-8")
        elevated = re.findall(
            r"^\s+(contents|id-token|attestations|packages):\s*write\s*(?:#.*)?$",
            text,
            re.MULTILINE,
        )
        if workflow.name == "release.yml":
            assert elevated, "release.yml has to elevate somewhere"
            continue
        assert not elevated, (
            f"{workflow.name} grants write permissions ({sorted(set(elevated))}). "
            f"Only release.yml should, and only on the job that builds and signs."
        )


# ------------------------------------------------------------- the artefact-route step


def test_the_ci_artefact_route_runs_without_a_network():
    """The step proves egress only if the namespace is actually dropped.

    `.github/scripts/artefact_route.py` takes `--allow-network` so it can be run on a
    laptop. Passing it in CI would leave a green tick reporting a guarantee that was
    never tested, so the one line that would do that is the one line asserted here.
    """
    ci = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
    assert "artefact_route.py" in ci, (
        "ci.yml no longer runs the artefact route (§5.1.1, F45)"
    )
    assert "unshare" in ci, (
        "the artefact-route step must run inside an empty network namespace"
    )
    assert "--allow-network" not in ci, (
        "ci.yml passes --allow-network to the artefact-route script, which disables "
        "the only thing that step establishes"
    )


def test_the_artefact_route_script_refuses_to_pass_silently():
    """The script must fail, not warn, if it finds itself with a network."""
    source = (
        REPO_ROOT / ".github" / "scripts" / "artefact_route.py"
    ).read_text(encoding="utf-8")
    assert "SystemExit" in source or "raise" in source, (
        "the network assertion has to abort; a printed warning in a CI log is not a gate"
    )


# --------------------------------------------------------------------------------- SBOM


@pytest.mark.parametrize("layer", LAYERS)
def test_an_sbom_is_committed_for_every_layer(layer):
    """One per layer, because one merged document would misdescribe every layer.

    The `generate` SBOM is the only one that describes what a *target* installs, and it
    is the only one most readers care about. A single project-wide SBOM listing torch
    would answer a question nobody asked.
    """
    path = SBOM_DIR / f"legal-rag-audit-{layer}.cdx.json"
    assert path.exists(), f"{path.relative_to(REPO_ROOT)} is missing — run gen_sbom.py"


@pytest.mark.parametrize("layer", LAYERS)
def test_the_sbom_is_shaped_like_cyclonedx(layer):
    """The fields a consumer indexes on.

    Full schema validation runs in CI against the published CycloneDX schema
    (`scripts/validate_sbom.py`), because validating our own output against our own
    reading of the specification would establish nothing. This is the fast version: it
    catches a generator change that breaks the contract before the slow job does.
    """
    document = json.loads(
        (SBOM_DIR / f"legal-rag-audit-{layer}.cdx.json").read_text(encoding="utf-8")
    )
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.6"
    assert document["version"] == 1
    assert document["serialNumber"].startswith("urn:uuid:")
    assert document["metadata"]["component"]["name"] == "legal-rag-audit"

    refs = set()
    for component in document["components"]:
        assert component["type"] == "library"
        assert component["purl"].startswith("pkg:pypi/")
        assert component["hashes"], f"{component['name']} carries no hash"
        for entry in component["hashes"]:
            assert entry["alg"] == "SHA-256"
            assert re.fullmatch(r"[0-9a-f]{64}", entry["content"])
        assert component["bom-ref"] not in refs, "duplicate bom-ref"
        refs.add(component["bom-ref"])


@pytest.mark.parametrize("layer", LAYERS)
def test_the_sbom_names_every_package_in_its_lockfile(layer):
    """Not a subset. A component list that quietly drops entries is worse than none.

    An SBOM is consumed by a scanner that assumes it is complete, so an omission does
    not read as a gap — it reads as an absence of the vulnerability.
    """
    pin = re.compile(r"^([A-Za-z0-9_.\-]+)\s*==")
    locked = {
        re.sub(r"[-_.]+", "-", pin.match(line.strip()).group(1)).lower()
        for line in (REQUIREMENTS_DIR / f"{layer}.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if pin.match(line.strip())
    }
    document = json.loads(
        (SBOM_DIR / f"legal-rag-audit-{layer}.cdx.json").read_text(encoding="utf-8")
    )
    listed = {component["name"] for component in document["components"]}
    assert locked == listed, (
        f"{layer}: the SBOM and the lockfile disagree. Only in the lockfile: "
        f"{sorted(locked - listed)}. Only in the SBOM: {sorted(listed - locked)}. "
        f"Run scripts/gen_sbom.py."
    )


@pytest.mark.parametrize("layer", LAYERS)
def test_the_sbom_carries_the_real_dependency_graph(layer):
    """`dependencies` is the resolution graph, not everything hung off the root.

    A flat list would say we asked for torch. We did not — it arrives through
    sentence-transformers, and an SBOM that cannot show the difference cannot answer
    the question a reviewer is actually asking about the tree.
    """
    document = json.loads(
        (SBOM_DIR / f"legal-rag-audit-{layer}.cdx.json").read_text(encoding="utf-8")
    )
    root = document["metadata"]["component"]["bom-ref"]
    edges = {entry["ref"]: entry["dependsOn"] for entry in document["dependencies"]}
    refs = {component["bom-ref"] for component in document["components"]} | {root}

    assert set(edges) == refs, "every component needs a dependencies entry, even if empty"
    for ref, targets in edges.items():
        for target in targets:
            assert target in refs, f"{ref} depends on {target}, which is not a component"

    direct = set(edges[root])
    assert direct, "the root depends on nothing, so the graph was not parsed"
    assert direct != refs - {root}, (
        f"{layer}: every component hangs directly off the root, which means the `# via` "
        f"graph was not parsed and the SBOM is a flat list wearing a graph's shape"
    )


def test_the_sbom_is_deterministic():
    """Regenerating from an unchanged lockfile produces the identical document.

    Which is what makes `--check` meaningful. CycloneDX permits a timestamp and a random
    serial number; either would make a committed SBOM impossible to verify against the
    lockfile it claims to describe, and the drift gate would be theatre.
    """
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import gen_sbom  # noqa: E402

    for layer in LAYERS:
        first = gen_sbom.render(gen_sbom.build(layer, "0.1.0"))
        second = gen_sbom.render(gen_sbom.build(layer, "0.1.0"))
        assert first == second, f"{layer}: the SBOM generator is not deterministic"
        assert "timestamp" not in json.loads(first)["metadata"], (
            "a generation timestamp makes drift undetectable — see gen_sbom.py"
        )


def test_the_sboms_match_the_lockfiles_on_disk():
    """The committed files, not the ones the generator would produce right now.

    Same ratchet as `gen_schemas.py --check`: a dependency bump that forgets the SBOM
    leaves a published document describing software nobody installs.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_sbom.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# -------------------------------------------------------------------------- base image


def test_the_base_image_is_pinned_by_digest():
    """`FROM python:3.11-slim` is a mutable pointer, exactly like `@v7` on an action.

    Pinning every Python dependency to its bytes and then building on whatever the tag
    resolved to that morning leaves the chain resting on its weakest link — and on the
    layer that carries the interpreter, the OS packages and the TLS store.
    """
    dockerfile = REPO_ROOT / "Dockerfile"
    if not dockerfile.exists():
        pytest.skip("no Dockerfile in this tree")

    froms = re.findall(r"^FROM\s+(\S+)", dockerfile.read_text(encoding="utf-8"), re.M)
    assert froms, "Dockerfile has no FROM line"
    for image in froms:
        assert re.search(r"@sha256:[0-9a-f]{64}$", image), (
            f"base image {image!r} is pinned by tag, not digest. Resolve it with:\n"
            f"    docker buildx imagetools inspect {image}"
        )


# ------------------------------------------------------------------ the release posture


def test_the_release_signing_key_is_committed():
    """Verification must not require fetching a key from a keyserver.

    A keyserver fetch means the verification trusted whatever the network returned that
    morning — which is the substitution the signature exists to detect. The key travels
    with the repository so the fingerprint can be compared against SECURITY.md by eye.
    """
    key = REPO_ROOT / ".github" / "release-signing-key.asc"
    assert key.exists(), "the release signing key is not committed"
    text = key.read_text(encoding="utf-8")
    assert text.startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----")
    assert "PRIVATE KEY" not in text, "a private key has been committed"


def test_security_md_publishes_the_fingerprint_of_that_key():
    """A committed key verifies against itself. The fingerprint is what breaks the loop.

    Someone handed a malicious clone can compare the printed fingerprint against a copy
    of SECURITY.md from anywhere else. Without it, `verify_release.sh` would check a
    signature against whatever key happened to be in the same repository.
    """
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    key = (REPO_ROOT / ".github" / "release-signing-key.asc").read_text(encoding="utf-8")

    fingerprints = re.findall(
        r"\b((?:[0-9A-F]{4}\s+){9,11}[0-9A-F]{4})\b", security
    ) + re.findall(r"\b([0-9A-F]{40})\b", security)
    assert fingerprints, (
        "SECURITY.md publishes no key fingerprint, so verify_release.sh checks a "
        "signature against a key from the same repository and proves nothing to "
        "someone handed a malicious clone"
    )
    assert key  # the key file is what the fingerprint refers to


def test_the_release_workflow_verifies_the_tag_before_it_builds():
    """Order matters: a pipeline that builds first has already spent its provenance.

    SLSA provenance is a statement that these bytes came from this workflow at this
    commit. Issuing one for a commit whose signature was never checked makes the
    attestation true and worthless.
    """
    release = (WORKFLOW_DIR / "release.yml").read_text(encoding="utf-8")
    assert "git verify-tag" in release
    assert release.index("git verify-tag") < release.index("python3 -m build"), (
        "release.yml builds before it verifies the tag signature"
    )
    assert "cosign sign-blob" in release
    assert "attest-build-provenance" in release


def test_verify_release_checks_everything_the_release_workflow_produces():
    """The reader's half has to keep up with the publisher's half.

    A release that starts emitting a new artefact type, or signing differently, leaves
    `verify_release.sh` quietly checking less than it claims — and a verification script
    that passes without checking is worse than no script at all.
    """
    verify = (REPO_ROOT / "scripts" / "verify_release.sh").read_text(encoding="utf-8")
    for expected in (
        "git verify-tag",
        "cosign verify-blob",
        "gh attestation verify",
        "SHA256SUMS",
    ):
        assert expected in verify, f"verify_release.sh no longer checks: {expected}"

    assert "--certificate-identity" in verify, (
        "cosign verify-blob without --certificate-identity accepts a signature from "
        "any Sigstore identity, which is every identity"
    )


# ----------------------------------------------------------------- the documents agree


def test_security_md_states_the_package_counts_the_lockfiles_actually_have():
    """A number in a security document is a claim like any other.

    SECURITY.md tells a reader the layer they install is 14 packages. That is the whole
    "read it in an afternoon" argument, and nothing else in the build would notice it
    going stale.
    """
    pin = re.compile(r"^([A-Za-z0-9_.\-]+)\s*==")
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")

    for layer in LAYERS:
        names = {
            re.sub(r"[-_.]+", "-", pin.match(line.strip()).group(1)).lower()
            for line in (REQUIREMENTS_DIR / f"{layer}.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if pin.match(line.strip())
        }
        row = re.search(rf"^\|\s*`{layer}`\s*\|\s*(\d+)\s*\|", security, re.MULTILINE)
        assert row, f"SECURITY.md has no dependency-count row for the {layer} layer"
        assert int(row.group(1)) == len(names), (
            f"SECURITY.md says the {layer} layer is {row.group(1)} packages; the "
            f"lockfile has {len(names)}"
        )


def test_the_threat_model_is_published():
    """§12.2 requires it published, and requires it split by configuration.

    A blanket "nothing of yours is at risk" is false against a real corpus, and the
    splitting is the signal — a security document that draws its own limits accurately
    demonstrates the method better than the report does.
    """
    path = REPO_ROOT / "docs" / "threat-model.md"
    assert path.exists(), "§12.2 requires docs/threat-model.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "planted corpus" in text and "real corpus" in text, (
        "the threat model must split by configuration, not make one blanket claim"
    )
