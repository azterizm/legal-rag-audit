"""The two images, and the invocation this project asks people to run (§12.3, NF3).

Split into two halves on purpose.

The first half reads the Dockerfiles, the workflows and the published documents. It is
fast, runs everywhere, and catches the failures that are actually likely: a base image
bumped in one file and not the other, a `latest` tag creeping into a release, a signing
step that signs a name instead of a digest.

The second half builds the image and runs things inside it. That is the half worth
having, because §5.3's boundary is a claim about what lands on somebody else's machine
and `tests/test_dependency_boundary.py` proves it about a virtualenv, not about the
artefact a client is handed. Skipped when Docker is not installed, and marked slow.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

GENERATE = REPO_ROOT / "Dockerfile.generate"
SCORE = REPO_ROOT / "Dockerfile.score"

#: Nothing in this list may be importable in the generate image. Same list as
#: tests/test_dependency_boundary.py, and deliberately so: the two modules prove the
#: same boundary about two different artefacts, and they should fail together or not
#: at all.
ML_STACK = ("torch", "transformers", "sentence_transformers", "numpy")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def instructions(path: Path) -> str:
    """The file with its comments removed.

    Both Dockerfiles explain the boundary in prose, and the prose names the packages
    the boundary keeps out. A test that greps the whole file would fail on the sentence
    describing what it is checking, which is the sort of test that gets loosened rather
    than fixed.
    """
    return "\n".join(
        line for line in read(path).splitlines() if not line.lstrip().startswith("#")
    )


# ------------------------------------------------------------------------ the split


def test_there_are_two_dockerfiles_and_not_one():
    """NF3 and §5.2. One image carrying both dependency sets is the thing being fixed.

    The single `Dockerfile` this replaced installed `requirements/score.txt` and said in
    its own header that it was not what a target should be asked to run — a warning in a
    comment, on the artefact somebody would have run.
    """
    assert GENERATE.exists(), "Dockerfile.generate is missing"
    assert SCORE.exists(), "Dockerfile.score is missing"
    assert not (REPO_ROOT / "Dockerfile").exists(), (
        "the undivided Dockerfile is back. It carried the ML stack, which is what "
        "§5.3 exists to keep off a target's machine"
    )


def test_the_generate_image_installs_the_generate_layer_and_nothing_else():
    text = instructions(GENERATE)
    assert "requirements/generate.txt" in text
    assert "requirements/score.txt" not in text, (
        "Dockerfile.generate installs the score lockfile. That is the whole boundary, "
        "gone in one line"
    )
    assert "sentence-transformers" not in text
    assert "torch" not in text


def test_the_score_image_installs_the_score_layer():
    assert "requirements/score.txt" in instructions(SCORE)


@pytest.mark.parametrize("path", [GENERATE, SCORE], ids=["generate", "score"])
def test_dependencies_are_installed_hash_verified(path):
    """--require-hashes, or a substituted artefact reaches a run instead of failing."""
    assert "--require-hashes" in read(path)


@pytest.mark.parametrize("path", [GENERATE, SCORE], ids=["generate", "score"])
def test_the_package_is_installed_without_resolving_or_fetching_a_backend(path):
    """`--no-deps` and `--no-build-isolation`, and the second one is the interesting one.

    PEP 517 build isolation downloads setuptools at build time. A build that fetches its
    own backend over the network has an unpinned link in it, which is what every other
    line in these files is there to remove. Without isolation the backend is the
    setuptools inside the base image, fixed by the same digest as the interpreter.
    """
    text = read(path)
    assert "--no-deps" in text
    assert "--no-build-isolation" in text


# ------------------------------------------------------------------- the base image


@pytest.mark.parametrize("path", [GENERATE, SCORE], ids=["generate", "score"])
def test_the_base_image_is_pinned_by_digest(path):
    """`python:3.11-slim` is a mutable pointer, exactly like `@v7` on an action.

    Pinning every Python dependency to its bytes and then building on whatever the tag
    resolved to that morning leaves the chain resting on its weakest link — and on the
    layer that carries the interpreter, the OS packages and the TLS store.
    """
    text = read(path)
    refs = re.findall(r"^(?:FROM|ARG BASE=)\s*(\S+)", text, re.M)
    concrete = [r for r in refs if not r.startswith("${")]
    assert concrete, f"{path.name} pins no base image"
    for image in concrete:
        assert re.search(r"@sha256:[0-9a-f]{64}$", image), (
            f"base image {image!r} is pinned by tag, not digest. Resolve it with:\n"
            f"    docker buildx imagetools inspect {image}"
        )


def test_both_images_are_built_on_the_same_base_digest():
    """They are bumped together or the split stops meaning anything.

    Two base images means two OS package sets, two TLS stores and two scan results, and
    a `trivy image` finding against one that silently does not apply to the other. The
    comment in each file says to update both; this is what makes that true.
    """
    def digest(path):
        return re.findall(r"@(sha256:[0-9a-f]{64})", read(path))

    assert digest(GENERATE), "Dockerfile.generate has no base digest"
    assert set(digest(GENERATE)) == set(digest(SCORE)), (
        "the two Dockerfiles are on different base images. Bump both together:\n"
        "    docker buildx imagetools inspect python:3.11-slim"
    )


# ----------------------------------------------------------------------- the runtime


@pytest.mark.parametrize("path", [GENERATE, SCORE], ids=["generate", "score"])
def test_the_image_does_not_run_as_root(path):
    """§12.3. An invocation that forgets `--user` must still not be root."""
    users = re.findall(r"^USER\s+(\S+)", read(path), re.M)
    assert users, f"{path.name} declares no USER, so it runs as root"
    assert users[-1] != "root" and not users[-1].startswith("0:"), users


@pytest.mark.parametrize("path", [GENERATE, SCORE], ids=["generate", "score"])
def test_no_volume_is_declared_for_the_output_directory(path):
    """A declared VOLUME turns a forgotten `-v` into a silent success.

    Docker creates an anonymous volume, the run writes the report into it, the container
    exits, the volume goes with it, and nothing anywhere says so. Without the
    declaration the write hits the read-only rootfs and aborts naming the path — NF9
    applied to the container rather than to the code.
    """
    assert not re.search(r"^VOLUME\b", read(path), re.M), (
        f"{path.name} declares a VOLUME. A forgotten mount would then discard the "
        f"report instead of failing"
    )


def test_the_score_image_refuses_to_fetch_weights_at_run_time():
    """HF_HUB_OFFLINE=1. A cache miss must fail, not reach a model hub.

    Scoring that claimed to run offline and quietly fetched a checkpoint would be the
    one place the local-path claim failed, in the one place nobody looks.
    """
    assert "HF_HUB_OFFLINE=1" in read(SCORE)


# --------------------------------------------------------------------- the release


def test_the_release_workflow_builds_and_signs_both_images():
    text = read(REPO_ROOT / ".github" / "workflows" / "release.yml")
    assert "Dockerfile.generate" in text
    assert "Dockerfile.score" in text
    assert "cosign sign " in text, "the images are published but never signed"
    assert "attest-build-provenance" in text


def test_the_images_are_signed_by_digest_and_never_by_tag():
    """`cosign sign image:v0.2.0` signs whatever that tag resolves to at that moment.

    Which is a signature over a name rather than over bytes, and the name can be moved
    afterwards by anybody with write access to the registry.
    """
    text = read(REPO_ROOT / ".github" / "workflows" / "release.yml")
    for line in text.splitlines():
        if "cosign sign " in line and not line.strip().startswith("#"):
            assert "@${{ steps." in line or "@sha256:" in line, (
                f"cosign signs a reference with no digest in it:\n    {line.strip()}"
            )


def test_no_mutable_latest_tag_is_published():
    """A pointer to "the current image" undoes the pinning in one line."""
    text = read(REPO_ROOT / ".github" / "workflows" / "release.yml")
    assert not re.search(r"^\s*tags:.*:latest", text, re.M), text


def test_the_release_records_the_tag_to_digest_mapping():
    """IMAGES is checksummed, signed and attested with everything else.

    Without it the mapping from a release tag to two digests lives only in a registry
    run by the same people who published the release, and "run this digest" is an
    instruction with nothing behind it.
    """
    text = read(REPO_ROOT / ".github" / "workflows" / "release.yml")
    assert "dist/IMAGES" in text
    verify = read(REPO_ROOT / "scripts" / "verify_release.sh")
    assert "IMAGES" in verify, "the release publishes IMAGES and nothing checks it"


def test_the_verifier_refuses_an_image_reference_without_a_digest():
    """A tag in IMAGES is a malformed release, and saying so is the answer.

    Verifying a tag would check a signature over whatever the registry returns today,
    which is the substitution the whole exercise exists to detect.
    """
    verify = read(REPO_ROOT / "scripts" / "verify_release.sh")
    assert "is a tag, not a digest" in verify


# ------------------------------------------------------------------ the image scan


def test_security_ci_scans_the_images_and_not_only_the_filesystem():
    """`trivy fs` sees the lockfiles. It does not see the base image's OS packages,
    which are most of what a CVE feed is about."""
    text = read(REPO_ROOT / ".github" / "workflows" / "security.yml")
    assert "scan-type: image" in text
    assert "scan-type: fs" in text, "the filesystem scan was replaced rather than joined"


def test_the_image_scan_keeps_the_two_layers_apart():
    """Same reason `pip-audit` runs per layer.

    An advisory in the generate image is a *target's* exposure, on a machine we do not
    own. One in the score image is ours. A merged pass/fail erases the distinction the
    architecture exists to make, and it is the generate result a client asks about.
    """
    text = read(REPO_ROOT / ".github" / "workflows" / "security.yml")
    assert "Dockerfile.${{ matrix.image }}" in text
    assert "fail-fast: false" in text, (
        "one image's failure would cancel the other's scan, so a red run would not say "
        "which layer the advisory is in"
    )


# ----------------------------------------------------------------- what we published


def test_the_hardened_invocation_is_documented_and_linked():
    doc = REPO_ROOT / "docs" / "hardened-run.md"
    assert doc.exists(), "§5.2's layout has named docs/hardened-run.md since the start"
    assert "docs/hardened-run.md" in read(REPO_ROOT / "README.md")


def test_no_published_document_prints_a_docker_flag_that_does_not_exist():
    """`--network=host-allowlist-only` was in the README, and there is no such network.

    It was standing in for *a network you configured to permit one destination*, which
    is a real thing that Docker cannot express as a flag. A reader who pasted it got an
    error, and the reasonable conclusion from an error is that the rest of the page is
    decorative too.
    """
    for doc in (REPO_ROOT / "README.md", *(REPO_ROOT / "docs").glob("*.md")):
        text = read(doc)
        for line in text.splitlines():
            if "--network=" not in line:
                continue
            value = line.split("--network=", 1)[1].split()[0].strip("\\`\"'")
            # `none` is Docker's own. Anything else has to be a network the reader
            # creates, and the document has to say how.
            if value != "none":
                assert "docker network create" in text, (
                    f"{doc.name} tells the reader to use --network={value} without "
                    f"saying where that network comes from"
                )


# ================================================================= building the image

docker = shutil.which("docker")
needs_docker = pytest.mark.skipif(docker is None, reason="docker is not installed")


def run(*args, **kwargs):
    return subprocess.run(
        [docker, *args], capture_output=True, text=True, timeout=1800, **kwargs
    )


@pytest.fixture(scope="module")
def generate_image():
    """Built from the repository, not pulled. The scan and the tests must agree with
    the working tree, not with whatever was published last month."""
    tag = "legal-rag-audit-generate:pytest"
    built = run("build", "-f", str(GENERATE), "-t", tag, str(REPO_ROOT))
    if built.returncode != 0:  # pragma: no cover - no daemon, or no network
        pytest.skip(f"could not build the generate image:\n{built.stderr[-800:]}")
    return tag


HARDENED = (
    "--rm",
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt",
    "no-new-privileges",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,size=64m",
)


@pytest.mark.slow
@needs_docker
@pytest.mark.parametrize("module", ML_STACK)
def test_the_ml_stack_is_not_importable_in_the_generate_image(generate_image, module):
    """The claim §5.3 makes, about the artefact rather than about a lockfile.

    A security reviewer is asking what lands on their machine. `pip-audit` and
    test_dependency_boundary answer that about a text file and a virtualenv; this
    answers it about the thing they would actually run.
    """
    result = run(
        "run", "--rm", "--network=none", "--entrypoint", "python",
        generate_image, "-c", f"import {module}",
    )
    assert result.returncode != 0, (
        f"{module} imports inside the generate image. The dependency boundary is the "
        f"security claim, and this is the artefact the claim is about"
    )
    assert "ModuleNotFoundError" in result.stderr


@pytest.mark.slow
@needs_docker
def test_the_generate_image_runs_the_cli(generate_image):
    result = run("run", "--rm", "--network=none", generate_image, "--help")
    assert result.returncode == 0, result.stderr
    assert "validate" in result.stdout and "score" in result.stdout


@pytest.mark.slow
@needs_docker
def test_the_generate_image_does_not_run_as_root(generate_image):
    result = run("run", "--rm", "--network=none", "--entrypoint", "id", generate_image)
    assert result.returncode == 0, result.stderr
    assert "uid=0(" not in result.stdout, result.stdout


@pytest.mark.slow
@needs_docker
def test_the_artefact_route_runs_in_the_image_with_no_network(generate_image, tmp_path):
    """§5.1.1, end to end, inside the container a client would be handed.

    plant → hash → their harness → score, with `--network=none`, a read-only rootfs,
    every capability dropped and a non-root user. This is the strongest form of the
    offer: we mint the corpus and the answer key, you run your own harness against your
    own system, and none of our code ever sees your endpoint.

    The route script is mounted read-only rather than baked in — it is CI's, not the
    package's, and an image carrying its own test would be proving something about a
    file it shipped.
    """
    out = tmp_path / "out"
    out.mkdir()
    out.chmod(0o777)  # the container user is not the one that made this directory
    result = run(
        "run", *HARDENED, "--network=none",
        "-v", f"{REPO_ROOT / '.github' / 'scripts'}:/in:ro",
        "-v", f"{out}:/out",
        "--entrypoint", "python", generate_image, "/in/artefact_route.py",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "with no network reachable" in result.stdout
    summary = json.loads(result.stdout[result.stdout.index("{"):result.stdout.rindex("}") + 1])
    assert summary["pre_commitment"] == "verified"


@pytest.mark.slow
@needs_docker
def test_a_forgotten_output_mount_aborts_and_names_the_path(generate_image):
    """NF9 in the container. This was a traceback out of `pathlib` until it was not.

    A target's first experience of the tool should not be fifteen frames of stdlib
    because they left a `-v` off the command line.
    """
    result = run("run", *HARDENED, "--network=none", generate_image, "plant", "-o", "/out/x")
    assert result.returncode == 2, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "/out/x" in combined
    assert "path problem, not a finding" in combined
    assert "Traceback" not in combined


@pytest.mark.slow
@needs_docker
def test_an_internal_network_actually_denies_egress(generate_image):
    """docs/hardened-run.md's load-bearing claim, and the only one it can enforce.

    Docker has no per-container host allowlist. What it has is `--internal`, which
    removes the external route entirely — and the page tells people to build their
    egress control on top of that, so the property had better hold. Checked in both
    directions: a network with no route, and one with a route, from the same image.
    """
    net = "legal-rag-audit-pytest-internal"
    run("network", "rm", net)
    created = run("network", "create", "--internal", net)
    if created.returncode != 0:  # pragma: no cover - restricted daemon
        pytest.skip(f"could not create an internal network:\n{created.stderr[-400:]}")
    reach = (
        "import socket;s=socket.socket();s.settimeout(6);"
        "s.connect(('1.1.1.1',443));print('reached')"
    )
    try:
        denied = run("run", "--rm", f"--network={net}", "--entrypoint", "python",
                     generate_image, "-c", reach)
        assert denied.returncode != 0, "an --internal network let a container out"
        assert "unreachable" in denied.stderr.lower() or "timed out" in denied.stderr.lower()
    finally:
        run("network", "rm", net)


@pytest.mark.slow
@needs_docker
@pytest.mark.skipif(
    os.environ.get("LEGAL_RAG_AUDIT_DOCKER_SCORE") != "1",
    reason="building the score image downloads the ML stack; set "
           "LEGAL_RAG_AUDIT_DOCKER_SCORE=1 to run it. security.yml builds it on "
           "every push, with a layer cache",
)
def test_the_score_image_has_the_tier_two_stack():
    """The other side of the boundary. A boundary with nothing on the far side of it
    is an extra somebody has to remember not to install."""
    tag = "legal-rag-audit-score:pytest"
    built = run("build", "-f", str(SCORE), "-t", tag, str(REPO_ROOT))
    if built.returncode != 0:  # pragma: no cover
        pytest.skip(f"could not build the score image:\n{built.stderr[-800:]}")
    result = run(
        "run", "--rm", "--network=none", "--entrypoint", "python", tag,
        "-c", "import torch, sentence_transformers; print('tier 2 present')",
    )
    assert result.returncode == 0, result.stderr
    assert "tier 2 present" in result.stdout
