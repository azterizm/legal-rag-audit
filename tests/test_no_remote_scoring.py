"""Phase A regression gate — the remote-scoring path stays out of the package.

V2_FULL_PLAN.md §4.2 removes remote scoring from the published code path so that the
determinism and zero-exfiltration claims stand unqualified. These tests keep it removed.
Defect 1 in §19 is the reason: the path had been live while the README denied it.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "src" / "legal_rag_audit"
EXPERIMENTS_DIR = REPO_ROOT / "internal_experiments"

VENDOR_PATTERN = re.compile(
    r"gemini|openai|anthropic|generativelanguage|google\.generativeai"
    r"|GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|use_gemini",
    re.IGNORECASE,
)

# Modules that would let a scoring path open a socket. httpx and websockets are
# legitimate for the target-facing client, so they are not listed here; §5.1's
# no-network assertion for `score` arrives with the Phase B package split.
NETWORK_MODULES = {"requests", "urllib3", "aiohttp", "google", "openai", "anthropic"}


def package_python_files():
    return sorted(PACKAGE_DIR.rglob("*.py"))


@pytest.mark.parametrize("path", package_python_files(), ids=lambda p: p.name)
def test_no_vendor_markers_in_package(path):
    """No third-party inference vendor is named anywhere in the published package."""
    hits = VENDOR_PATTERN.findall(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.relative_to(REPO_ROOT)} names remote-scoring vendors: {hits}"


@pytest.mark.parametrize("path", package_python_files(), ids=lambda p: p.name)
def test_package_does_not_import_requests(path):
    """The evaluators score in-process. None of them reaches for an HTTP client."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    offending = imported & NETWORK_MODULES
    assert not offending, (
        f"{path.relative_to(REPO_ROOT)} imports {sorted(offending)}; scoring must not "
        f"perform network I/O"
    )


@pytest.mark.parametrize("path", package_python_files(), ids=lambda p: p.name)
def test_package_never_imports_internal_experiments(path):
    """The excluded module is unreachable from the shipped package."""
    assert "internal_experiments" not in path.read_text(encoding="utf-8"), (
        f"{path.relative_to(REPO_ROOT)} references internal_experiments, which is not "
        f"shipped in the wheel or the image"
    )


def test_cli_exposes_no_remote_scoring_flag():
    """`--use-gemini` and friends are gone from the command surface."""
    cli_source = (PACKAGE_DIR / "cli.py").read_text(encoding="utf-8")
    for flag in ("--use-gemini", "--gemini-model", "--allow-remote-scoring"):
        assert flag not in cli_source, f"{flag} is still on the CLI"


def test_internal_experiments_excluded_from_wheel():
    """Exclusion is declared, not assumed."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    packages_line = re.search(r"^\s*packages\s*=.*$", pyproject, re.MULTILINE)
    assert packages_line, (
        "pyproject.toml must declare an explicit packages list, otherwise setuptools "
        "discovery would pick up internal_experiments/ and ship it"
    )
    assert "internal_experiments" not in packages_line.group(0)


def test_internal_experiments_excluded_from_pytest_collection():
    """The manual scripts need a live API key; pytest must never try to run them."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    norecurse = re.search(r"^\s*norecursedirs\s*=.*$", pyproject, re.MULTILINE)
    assert norecurse and "internal_experiments" in norecurse.group(0)


def test_internal_experiments_excluded_from_image():
    dockerignore = REPO_ROOT / ".dockerignore"
    assert dockerignore.exists(), ".dockerignore is the image-side exclusion mechanism"
    assert "internal_experiments/" in dockerignore.read_text(encoding="utf-8")


def test_experiments_module_is_documented_as_excluded():
    """A reader who finds the vendor code finds the reason it is quarantined."""
    readme = (EXPERIMENTS_DIR / "README.md").read_text(encoding="utf-8")
    assert "NOT part of the published tool" in readme


def test_readme_claims_are_scoped():
    """Every determinism and exfiltration claim in the README carries its scope."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_readme_claims.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
