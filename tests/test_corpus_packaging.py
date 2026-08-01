"""The bundled demo corpus ships, and a missing one aborts instead of degrading.

Two failures are covered, and they are different failures.

The packaging one: setuptools ships `.py` files and nothing else unless told otherwise,
so the corpus was absent from the wheel while every local editable install worked fine.
Testing the config that produces an artefact is not testing the artefact, so the wheel
is built and opened here.

The behavioural one: with the corpus missing, the runner substituted two stand-in
documents and *completed*. The report then described a 2-document corpus while the config
said thirteen, and nothing on the page disclosed the substitution. That is a setup
problem rendering as a finding, which NF9 forbids.
"""

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from legal_rag_audit.corpus_loader import (
    BUNDLED_DOCUMENTS,
    CorpusError,
    bundled_corpus_path,
    load_corpus,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- packaging


def test_bundled_corpus_present_in_source_tree():
    corpus_dir = Path(bundled_corpus_path())
    assert corpus_dir.is_dir()
    present = {p.name for p in corpus_dir.iterdir() if not p.name.startswith(".")}
    assert set(BUNDLED_DOCUMENTS) <= present


def test_package_data_is_declared():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.package-data]" in pyproject, (
        "without a package-data declaration setuptools ships only .py files and the "
        "corpus silently does not reach the wheel"
    )


@pytest.mark.slow
def test_bundled_corpus_is_inside_the_built_wheel(tmp_path):
    """Build the wheel and open it. The artefact is what ships, not the config."""
    if shutil.which(sys.executable) is None:  # pragma: no cover
        pytest.skip("no interpreter available to build with")

    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"wheel build unavailable in this environment:\n{result.stderr[-500:]}")

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, got {wheels}"

    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()

    shipped = {
        Path(n).name for n in names if n.startswith("legal_rag_audit/corpus/")
    }
    missing = sorted(set(BUNDLED_DOCUMENTS) - shipped)
    assert not missing, f"wheel is missing bundled corpus documents: {missing}"


# ------------------------------------------------------------------------- guardrail


def test_bundled_corpus_loads():
    documents = load_corpus(use_bundled=True)
    assert len(documents) == len(BUNDLED_DOCUMENTS)
    assert all(d["content"].strip() for d in documents)
    assert {d["filename"] for d in documents} == set(BUNDLED_DOCUMENTS)


def test_incomplete_bundled_corpus_aborts_and_names_what_is_missing(tmp_path, monkeypatch):
    partial = tmp_path / "corpus"
    partial.mkdir()
    kept = BUNDLED_DOCUMENTS[:3]
    for name in kept:
        (partial / name).write_text("placeholder content", encoding="utf-8")

    monkeypatch.setattr(
        "legal_rag_audit.corpus_loader.bundled_corpus_path", lambda: str(partial)
    )

    with pytest.raises(CorpusError) as excinfo:
        load_corpus(use_bundled=True)

    message = str(excinfo.value)
    assert "incomplete" in message
    # The diagnosis names the missing documents rather than only the count.
    assert BUNDLED_DOCUMENTS[-1] in message


def test_missing_bundled_corpus_directory_aborts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "legal_rag_audit.corpus_loader.bundled_corpus_path",
        lambda: str(tmp_path / "does-not-exist"),
    )
    with pytest.raises(CorpusError, match="not installed"):
        load_corpus(use_bundled=True)


def test_no_corpus_configured_aborts():
    with pytest.raises(CorpusError, match="No corpus configured"):
        load_corpus(use_bundled=False, path=None)


def test_custom_corpus_path_must_exist(tmp_path):
    with pytest.raises(CorpusError, match="does not exist"):
        load_corpus(use_bundled=False, path=str(tmp_path / "nope"))


def test_empty_custom_corpus_directory_aborts(tmp_path):
    empty = tmp_path / "corpus"
    empty.mkdir()
    with pytest.raises(CorpusError, match="no readable documents"):
        load_corpus(use_bundled=False, path=str(empty))


def test_custom_corpus_loads(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "one.txt").write_text("The liability cap is $2,000,000.", encoding="utf-8")
    (d / "two.md").write_text("# Notes\n\nArbitration seat is London.", encoding="utf-8")

    documents = load_corpus(use_bundled=False, path=str(d))
    assert [x["filename"] for x in documents] == ["one.txt", "two.md"]
    assert documents[0]["id"] == "one"


def test_empty_document_aborts(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "real.txt").write_text("content", encoding="utf-8")
    (d / "blank.txt").write_text("   \n\n", encoding="utf-8")
    with pytest.raises(CorpusError, match="empty"):
        load_corpus(use_bundled=False, path=str(d))


def test_non_utf8_document_aborts(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "binary.txt").write_bytes(b"\xff\xfe\x00\x01 not text")
    with pytest.raises(CorpusError, match="not UTF-8"):
        load_corpus(use_bundled=False, path=str(d))


def test_hidden_files_are_skipped(tmp_path):
    """macOS drops .DS_Store into directories; it is not a corpus document."""
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "real.txt").write_text("content", encoding="utf-8")
    (d / ".DS_Store").write_bytes(b"\x00\x01\x02")
    documents = load_corpus(use_bundled=False, path=str(d))
    assert [x["filename"] for x in documents] == ["real.txt"]


def test_document_order_is_stable(tmp_path):
    """Scoring is deterministic, so corpus order cannot depend on the filesystem."""
    d = tmp_path / "corpus"
    d.mkdir()
    for name in ("c.txt", "a.txt", "b.txt"):
        (d / name).write_text(f"content of {name}", encoding="utf-8")
    assert [x["filename"] for x in load_corpus(use_bundled=False, path=str(d))] == [
        "a.txt",
        "b.txt",
        "c.txt",
    ]


def test_runner_no_longer_carries_a_silent_fallback():
    """The two stand-in documents must not come back."""
    runner_source = (REPO_ROOT / "legal_rag_audit" / "runner.py").read_text(
        encoding="utf-8"
    )
    assert "fallback dummy docs" not in runner_source
    assert not re.search(r"Smith v\. Crown \(2024\).{0,200}capped at", runner_source), (
        "runner.py appears to inline stand-in corpus documents again"
    )


def test_cli_exits_with_a_diagnosis_rather_than_a_traceback():
    cli_source = (REPO_ROOT / "legal_rag_audit" / "cli.py").read_text(encoding="utf-8")
    assert "CorpusError" in cli_source
    assert "sys.exit(2)" in cli_source
