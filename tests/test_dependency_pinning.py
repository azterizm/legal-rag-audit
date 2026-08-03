"""Dependencies are exactly pinned, hash-verified, and split by mode.

NF11 says a third party reconstructs the run from the manifest and the repository at a
signed commit. A range makes that false: `sentence-transformers>=2.2.2` is different
software in March than in August, and a Tier 2 threshold means nothing without the model
and library version behind it. A range also turns `pip-audit` into a statement about the
day someone installed rather than about the artefact — which is how `idna==3.11`
(PYSEC-2026-215) was present locally while the declared set looked fine.

§5.3 additionally requires the generate/validate dependency set to stay free of the ML
stack, so a target can read the whole thing rather than take it on faith.
"""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_DIR = REPO_ROOT / "requirements"
#: `audit` joined in Phase B2 — the CI-only security scanners. It is held to the same
#: standard as the shipped layers: a scanner resolved at CI time is a statement about
#: whatever was current that morning, which is the class of claim this project refuses
#: to make about anything else.
LAYERS = ("generate", "score", "dev", "audit")

PIN_RE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s;\\]+)")

# The ML stack must be unreachable from the generate/validate set.
ML_PACKAGES = {
    "torch",
    "transformers",
    "sentence-transformers",
    "scikit-learn",
    "scipy",
    "numpy",
    "huggingface-hub",
    "safetensors",
    "tokenizers",
}


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_packages(layer: str) -> dict[str, set[str]]:
    path = REQUIREMENTS_DIR / f"{layer}.txt"
    pins: dict[str, set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "--hash")):
            continue
        match = PIN_RE.match(stripped)
        if match:
            pins.setdefault(normalise(match.group(1)), set()).add(match.group(2))
    return pins


@pytest.mark.parametrize("layer", LAYERS)
def test_lockfile_exists(layer):
    assert (REQUIREMENTS_DIR / f"{layer}.txt").exists(), (
        f"requirements/{layer}.txt is missing; regenerate with scripts/lock.sh"
    )
    assert (REQUIREMENTS_DIR / f"{layer}.in").exists(), (
        f"requirements/{layer}.in is missing; the .txt is generated, not authored"
    )


@pytest.mark.parametrize("layer", LAYERS)
def test_every_lockfile_entry_is_exact(layer):
    """No ranges. Not one."""
    loose = []
    for lineno, line in enumerate(
        (REQUIREMENTS_DIR / f"{layer}.txt").read_text(encoding="utf-8").splitlines(), 1
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "--hash", "-r", "-c")):
            continue
        if PIN_RE.match(stripped):
            continue
        if re.search(r"(>=|<=|~=|!=|\s>|\s<)", stripped):
            loose.append(f"{lineno}: {stripped}")
    assert not loose, f"requirements/{layer}.txt has loose specifiers:\n" + "\n".join(loose)


@pytest.mark.parametrize("layer", LAYERS)
def test_every_lockfile_entry_is_hashed(layer):
    """A pin fixes what was asked for; a hash fixes what was received."""
    text = (REQUIREMENTS_DIR / f"{layer}.txt").read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=[A-Za-z0-9_.\-]+\s*==)", text)
    unhashed = [
        PIN_RE.match(b.strip()).group(0)
        for b in blocks
        if PIN_RE.match(b.strip()) and "--hash=" not in b
    ]
    assert not unhashed, (
        f"requirements/{layer}.txt entries without hashes: {unhashed[:10]}\n"
        f"--require-hashes cannot protect what is not hashed."
    )


def test_pyproject_declares_no_ranges():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)

    loose = [r for r in requirements if not PIN_RE.match(r.strip())]
    assert not loose, (
        f"pyproject.toml declares non-exact requirements: {loose}\n"
        f"`pip install -e .` must produce the same versions for everyone."
    )
    assert requirements, "pyproject.toml declares no dependencies at all"


def test_pyproject_pins_match_the_lockfiles():
    """Two sources of truth that disagree are worse than one that is vague."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_pins.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generate_layer_carries_no_ml_stack():
    """§5.3 — the set a target installs stays reviewable."""
    generate = set(locked_packages("generate"))
    leaked = sorted(generate & ML_PACKAGES)
    assert not leaked, (
        f"requirements/generate.txt pulls the ML stack: {leaked}\n"
        f"generate/validate must stay on pure-Python dependencies so a target can read "
        f"the whole tree."
    )


def test_score_layer_is_a_superset_of_generate():
    """score runs everything generate does, plus the models. Versions must not fork."""
    generate, score = locked_packages("generate"), locked_packages("score")
    missing = sorted(set(generate) - set(score))
    assert not missing, f"requirements/score.txt is missing {missing}"

    conflicts = {
        name: (generate[name], score[name])
        for name in generate
        if generate[name] != score[name]
    }
    assert not conflicts, (
        f"generate and score pin different versions of the same package: {conflicts}"
    )


def test_generate_layer_stays_small():
    """NF8 — 'readable end to end in ten minutes' has to stay literally true."""
    count = len(locked_packages("generate"))
    assert count <= 25, (
        f"requirements/generate.txt has grown to {count} packages. The reviewability "
        f"claim is load-bearing; if this is intentional, move the claim first."
    )


def test_requirements_are_generated_not_authored():
    """A hand-edited lockfile is a lockfile nobody can regenerate."""
    for layer in LAYERS:
        text = (REQUIREMENTS_DIR / f"{layer}.in").read_text(encoding="utf-8")
        assert "scripts/lock.sh" in text, (
            f"requirements/{layer}.in should tell the next reader how to regenerate"
        )


def test_idna_is_pinned_above_the_known_advisory():
    """Regression: PYSEC-2026-215 was reachable through an unpinned httpx dependency."""
    versions = locked_packages("generate").get("idna")
    assert versions, "idna is not pinned in the generate layer"
    for version in versions:
        major, minor = (int(p) for p in version.split(".")[:2])
        assert (major, minor) >= (3, 15), f"idna=={version} is below the PYSEC-2026-215 fix"
