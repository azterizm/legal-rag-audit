"""The generate layer installs without the ML stack, and still works (F31, §5.3).

`tests/test_dependency_pinning.py` asserts this about the *lockfiles* — that torch is
absent from `requirements/generate.txt`. That is a statement about a text file. This
module builds the environment and imports things in it, because the claim being made to
a security reviewer is about what lands on their machine, not about what we wrote down.

Slow: it creates a virtualenv and installs fourteen packages. Skipped by `-m 'not slow'`.
"""

import json
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


# ------------------------------------------------------- the artefact route (F45)


@pytest.mark.slow
def test_the_whole_artefact_route_runs_with_no_transport_installed(
    generate_env, tmp_path
):
    """§5.1.1, end to end, in an environment that cannot reach a network.

    The route a target takes when they will not point our software at a live system:
    they hold the endpoint, we hold nothing of theirs, and what comes back is a file.
    Asserted structurally rather than promised, because a change that reintroduced the
    coupling would otherwise be discovered by a client rather than by the build.

    `httpx` is uninstalled first, so `plant`, `hash` and `score` are proved not to reach
    the transport layer even transitively. The response file is written by hand — no
    `generate`, no `Generator`, no config — and it still scores in full.
    """
    subprocess.run(
        [str(generate_env), "-m", "pip", "uninstall", "--quiet", "-y", "httpx"],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        assert run_in(generate_env, "import httpx").returncode != 0

        script = tmp_path / "artefact_route.py"
        script.write_text(
            "import json, sys\n"
            "from legal_rag_audit.interchange import (CaptureNotes, Response,\n"
            "    write_ground_truth, write_probes, write_responses)\n"
            "from legal_rag_audit.plants import plant, write_corpus\n"
            "from legal_rag_audit.probes import build_ground_truth, build_probes\n"
            "from legal_rag_audit.provenance import build_handover\n"
            "from legal_rag_audit.interchange import write_handover\n"
            "from legal_rag_audit.score import score\n"
            "d = sys.argv[1]\n"
            # 1. plant — no network
            "corpus = plant('artefact-route-seed')\n"
            "write_corpus(d + '/corpus', corpus)\n"
            "probes = build_probes(corpus=corpus)\n"
            "write_probes(d + '/probes.jsonl', probes)\n"
            "write_ground_truth(d + '/gt.json', build_ground_truth(corpus))\n"
            # 2. hash — no network
            "write_handover(d + '/handover.json', build_handover(\n"
            "    corpus=d + '/corpus', probes=d + '/probes.jsonl',\n"
            "    ground_truth=d + '/gt.json'))\n"
            # 3. their harness, standing in for anything that emits the format
            "notes = CaptureNotes(record='capture_notes', citations_captured=False,\n"
            "    retrieved_chunks_captured=False)\n"
            "write_responses(d + '/r.jsonl', [Response(run_id='theirs',\n"
            "    probe_id=p.probe_id, query=p.text, tenant=p.tenant,\n"
            "    answer='Our harness produced this.') for p in probes],\n"
            "    capture_notes=notes)\n"
            # 4. score — no network, and the pre-commitment still verifies
            "report = score(d + '/r.jsonl', d + '/gt.json', d + '/probes.jsonl',\n"
            "    skip_tier2=True, handover_path=d + '/handover.json',\n"
            "    output_dir=d + '/out')\n"
            "print(json.dumps({\n"
            "    'checks': report['summary']['checks_registered'],\n"
            "    'pre_commitment': report['manifest']['pre_commitment']['status'],\n"
            "    'verbatim': report['manifest']['capture']['probes_asked_verbatim'],\n"
            "}))\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(generate_env), str(script), str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        out = json.loads(result.stdout)
        assert out["checks"] == 17, "every check is reported, none omitted"
        assert out["pre_commitment"] == "verified", (
            "the pre-commitment holds on the artefact route — the corpus, probes and "
            "answer key were sealed before any answer existed"
        )
        assert out["verbatim"] == len(
            [line for line in (tmp_path / "r.jsonl").read_text().splitlines()][1:]
        )
        assert (tmp_path / "out" / "report.md").exists()
    finally:
        subprocess.run(
            [
                str(generate_env), "-m", "pip", "install", "--quiet",
                "--require-hashes", "-r",
                str(REPO_ROOT / "requirements" / "generate.txt"),
            ],
            capture_output=True,
            text=True,
        )
