"""The generate layer installs without the ML stack, and still works (F31, §5.3).

`tests/test_dependency_pinning.py` asserts this about the *lockfiles* — that torch is
absent from `requirements/generate.txt`. That is a statement about a text file. This
module builds the environment and imports things in it, because the claim being made to
a security reviewer is about what lands on their machine, not about what we wrote down.

Slow: it creates a virtualenv and installs fourteen packages. Skipped by `-m 'not slow'`.
"""

import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Nothing in this list may be importable in a generate-layer environment. They are the
#: packages that make the dependency tree unreviewable — the reason the boundary exists
#: rather than an arbitrary denylist.
ML_STACK = ("torch", "transformers", "sentence_transformers", "numpy")


@pytest.fixture(scope="module")
def generate_env(tmp_path_factory):
    """A virtualenv holding exactly the generate layer, plus the package itself."""
    root = tmp_path_factory.mktemp("generate-layer")
    env_dir = root / "venv"
    venv.create(env_dir, with_pip=True)
    python = env_dir / "bin" / "python"
    if not python.exists():  # pragma: no cover - Windows
        python = env_dir / "Scripts" / "python.exe"

    install = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--require-hashes",
            "-r",
            str(REPO_ROOT / "requirements" / "generate.txt"),
        ],
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:  # pragma: no cover - offline or index unavailable
        pytest.skip(f"could not install the generate layer:\n{install.stderr[-600:]}")

    # --no-deps: the lockfile above is the whole installed set. Without it pip
    # re-resolves from pyproject.toml, and the test would be measuring pip's opinion
    # rather than the boundary.
    package = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--no-deps", str(REPO_ROOT)],
        capture_output=True,
        text=True,
    )
    assert package.returncode == 0, package.stderr

    return python


def run_in(python: Path, code: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(python), "-c", code], capture_output=True, text=True)


@pytest.mark.slow
@pytest.mark.parametrize("module", ML_STACK)
def test_the_ml_stack_is_absent(generate_env, module):
    result = run_in(generate_env, f"import {module}")
    assert result.returncode != 0, (
        f"{module} is importable in a generate-layer environment. The boundary in §5.3 "
        f"is what makes 'read it in an afternoon' true; a base install that reaches the "
        f"ML stack breaks the claim rather than the code."
    )
    assert "ModuleNotFoundError" in result.stderr


@pytest.mark.slow
def test_generate_imports_and_runs_there(generate_env):
    """The mode a target actually runs has to work in the environment they install."""
    result = run_in(
        generate_env,
        "from legal_rag_audit.generate import generate;"
        "from legal_rag_audit.config import AuditConfig;"
        "from legal_rag_audit.transport import TargetClient;"
        "from legal_rag_audit.probes import build_probes, validate_battery;"
        "validate_battery();"
        "print(len(build_probes()))",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().isdigit()


@pytest.mark.slow
def test_the_cli_runs_there(generate_env):
    result = run_in(
        generate_env,
        "import sys;"
        "sys.argv=['legal-rag-audit','schema','--list'];"
        "from legal_rag_audit.cli import main;"
        "main()",
    )
    # main() calls sys.exit(0) on success.
    assert result.returncode == 0, result.stderr
    assert "responses.v2" in result.stdout


@pytest.mark.slow
def test_the_scoring_registry_imports_without_the_ml_stack(generate_env):
    """Importing the registry must not drag in the Tier 2 modules.

    This is the regression the lazy `evaluators/__init__` exists for: it re-exported all
    seventeen eagerly, so importing the registry — to read tiers, or to run a Tier 1
    check — imported sentence_transformers and failed here.
    """
    result = run_in(
        generate_env,
        "from legal_rag_audit.score.registry import REGISTRY, tier1_checks;"
        "print(len(REGISTRY), len(tier1_checks()))",
    )
    assert result.returncode == 0, result.stderr
    registered, tier1 = (int(x) for x in result.stdout.split())
    assert registered == 17
    # 15 of the 18 evaluators in §8.1 are Tier 1 and shipped; #18 arrives in Phase G to
    # make 16. The count moved from 14 when Phase D rewrote abstention as an inverted
    # presence check and took the cross-encoder out of its path (§8.2 #8).
    assert tier1 == 15


@pytest.mark.slow
def test_a_tier1_check_scores_without_the_ml_stack(generate_env, tmp_path):
    """The point of the boundary, end to end: Tier 1 scoring in a torch-free install."""
    script = tmp_path / "score_tier1.py"
    script.write_text(
        "import json, sys\n"
        "from legal_rag_audit.interchange import Response, write_ground_truth, "
        "write_probes, write_responses\n"
        "from legal_rag_audit.probes import build_ground_truth, build_probes\n"
        "from legal_rag_audit.score import score\n"
        "d = sys.argv[1]\n"
        "probes = build_probes()\n"
        "write_probes(d + '/p.jsonl', probes)\n"
        "write_ground_truth(d + '/gt.json', build_ground_truth())\n"
        "write_responses(d + '/r.jsonl', [Response(run_id='r', probe_id=p.probe_id,"
        " query=p.text, answer='An answer.') for p in probes])\n"
        "report = score(d + '/r.jsonl', d + '/gt.json', d + '/p.jsonl', "
        "skip_tier2=True)\n"
        "print(report['summary']['checks_registered'])\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(generate_env), str(script), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "17"


@pytest.mark.slow
def test_tier2_fails_with_an_instruction_rather_than_a_bare_import_error(generate_env):
    """A missing scoring layer is our setup problem, and the message has to say so."""
    result = run_in(
        generate_env,
        "from legal_rag_audit.evaluators import HallucinationEvaluator",
    )
    assert result.returncode != 0
    assert "requirements/score.txt" in result.stderr
    assert "Tier 2" in result.stderr


def test_pyproject_keeps_the_ml_stack_out_of_the_base_set():
    """The fast version of the above, so a wrong edit fails before the slow tests run."""
    import tomllib

    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    base = " ".join(pyproject["project"]["dependencies"]).lower()
    for package in ("sentence-transformers", "torch", "transformers"):
        assert package not in base, (
            f"{package} is a base dependency; it belongs behind the score extra"
        )
    extras = pyproject["project"].get("optional-dependencies", {})
    assert "score" in extras, "the ML stack needs an extra to live in"
    assert any("sentence-transformers" in r for r in extras["score"])
