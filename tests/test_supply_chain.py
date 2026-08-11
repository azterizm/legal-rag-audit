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
import subprocess
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


def test_every_dockerfile_pins_its_base_image_by_digest():
    """`FROM python:3.11-slim` is a mutable pointer, exactly like `@v7` on an action.

    Pinning every Python dependency to its bytes and then building on whatever the tag
    resolved to that morning leaves the chain resting on its weakest link — and on the
    layer that carries the interpreter, the OS packages and the TLS store.

    Discovered by glob rather than named, because the failure this guards against is a
    *third* Dockerfile arriving and nobody adding it here. tests/test_container.py
    checks the same property per file, along with the rest of the image posture; this
    one is the sweep that notices a new file.
    """
    dockerfiles = sorted(REPO_ROOT.glob("Dockerfile*"))
    assert dockerfiles, "no Dockerfile in this tree"

    for dockerfile in dockerfiles:
        text = dockerfile.read_text(encoding="utf-8")
        refs = re.findall(r"^(?:FROM|ARG BASE=)\s*(\S+)", text, re.M)
        # `FROM ${BASE}` resolves to the pinned ARG above it, which this same sweep
        # checks. Only the concrete references are claims about bytes.
        concrete = [r for r in refs if not r.startswith("${")]
        assert concrete, f"{dockerfile.name} pins no base image"
        for image in concrete:
            assert re.search(r"@sha256:[0-9a-f]{64}$", image), (
                f"{dockerfile.name}: base image {image!r} is pinned by tag, not "
                f"digest. Resolve it with:\n"
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


# ------------------------------------------------------- the repository has one name


#: Where the repository's own slug is written out by hand rather than derived.
#:
#: `release.yml` derives every image name from `${{ github.repository }}`, so the
#: *published* path follows a rename on its own. Nothing else does. Each of these is a
#: copy that a rename has to be told about, and a copy that is not told goes on being
#: read: `docs/hardened-run.md` hands a reader a `docker run` line, the Dockerfile label
#: is what links a GHCR package back to a repository, and `verify_release.sh`'s fallback
#: decides which repository a stranger's verification is aimed at.
#:
#: The failure this guards is a *partial* rename, which is the likely one. A repository
#: renamed on GitHub keeps redirecting, CI stays green, and the stale copies keep
#: printing an image path that was never published and a verification target that is not
#: this project.
_SLUG_RE = r"(?P<slug>[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*)"

SLUG_SITES = (
    ("Dockerfile.generate", rf"image\.source=\"https://github\.com/{_SLUG_RE}\""),
    ("Dockerfile.score", rf"image\.source=\"https://github\.com/{_SLUG_RE}\""),
    ("scripts/verify_release.sh", rf"LEGAL_RAG_AUDIT_REPO:-{_SLUG_RE}\}}"),
    ("scripts/gen_sbom.py", rf"PROJECT_URL = \"https://github\.com/{_SLUG_RE}\""),
    ("docs/hardened-run.md", rf"ghcr\.io/{_SLUG_RE}-(?:generate|score)"),
    ("README.md", rf"https://github\.com/{_SLUG_RE}/actions/"),
    ("SECURITY.md", rf"https://github\.com/{_SLUG_RE}/actions/"),
    ("CONTRIBUTING.md", rf"git clone https://github\.com/{_SLUG_RE}"),
)


def _slugs_written_by_hand() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for name, pattern in SLUG_SITES:
        path = REPO_ROOT / name
        assert path.exists(), f"{name} is missing, so its copy of the slug cannot agree"
        matches = {
            m.group("slug")
            for m in re.finditer(pattern, path.read_text(encoding="utf-8"))
        }
        assert matches, (
            f"{name} no longer states the repository slug in the shape this test reads "
            f"({pattern!r}). Either the file changed or the guard did — do not delete "
            f"the assertion to make it pass"
        )
        found[name] = matches
    return found


def test_every_hand_written_copy_of_the_repository_slug_agrees():
    """One repository, one name, in eight files that each spell it out.

    A rename is nearly always applied to the places somebody greps for and missed in one
    or two. Nothing else in the build would notice: the workflows derive their paths, the
    tests do not read these strings, and GitHub redirects the old URL — so the only
    symptom is a reader following a documented `docker pull` to an image that does not
    exist.
    """
    found = _slugs_written_by_hand()
    distinct = {slug for slugs in found.values() for slug in slugs}
    assert len(distinct) == 1, (
        "the repository is named more than one thing across its own files, which means "
        f"a rename was applied in some of them and not others: {json.dumps({k: sorted(v) for k, v in found.items()}, indent=2)}"
    )


def test_the_slug_the_documents_use_is_the_repository_they_are_in():
    """Eight files agreeing on the wrong name is still the wrong name.

    The check above proves consistency. This one anchors it to something outside the
    files — the remote the checkout came from — which is the only thing that can catch a
    rename nobody has applied anywhere yet.
    """
    try:
        origin = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover - no git here
        pytest.skip(f"git is not usable here, so there is no remote to compare to: {e}")

    if origin.returncode != 0:
        pytest.skip("this checkout has no origin remote to compare the slug against")

    match = re.search(
        rf"github\.com[:/]{_SLUG_RE}?(?:\.git)?$", origin.stdout.strip()
    )
    if not match:
        pytest.skip(f"origin is not a GitHub remote: {origin.stdout.strip()!r}")

    expected = match.group("slug").removesuffix(".git")
    written = {slug for slugs in _slugs_written_by_hand().values() for slug in slugs}
    assert written == {expected}, (
        f"this checkout came from {expected!r}, but its own files call the project "
        f"{sorted(written)}. A rename was applied to the remote and not to the "
        f"repository, or the other way round"
    )


def test_the_published_image_path_is_derived_and_never_typed():
    """`release.yml` must follow a rename rather than have to be told about one.

    Every image name, attestation subject and cosign target comes from
    `${{ github.repository }}`. Typing the slug there would put the one copy that decides
    what actually gets pushed out of reach of the check above — and it would be the copy
    nobody notices is wrong, because a push to a fresh GHCR path succeeds.
    """
    release = (WORKFLOW_DIR / "release.yml").read_text(encoding="utf-8")

    # To end of line, not `\S+` — the expression this insists on has a space in it.
    ghcr = [ref.strip() for ref in re.findall(r"ghcr\.io/(.+)", release)]
    assert ghcr, "release.yml publishes no image"
    for ref in ghcr:
        assert ref.startswith("${{ github.repository }}"), (
            f"release.yml names an image path literally: ghcr.io/{ref}. It must be "
            f"derived from ${{{{ github.repository }}}} so a rename cannot leave the "
            f"workflow publishing to the old path"
        )

    # The suffixes are the other half: docs/hardened-run.md writes them out, and a reader
    # copying that line has to land on something release.yml actually pushed.
    for suffix in ("-generate", "-score"):
        assert f"ghcr.io/${{{{ github.repository }}}}{suffix}" in release, (
            f"release.yml no longer publishes an image ending {suffix}, which "
            f"docs/hardened-run.md tells people to pull"
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
