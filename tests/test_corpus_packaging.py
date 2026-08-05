"""The corpus library ships, and a missing corpus aborts instead of degrading.

Two failures are covered, and they are different failures.

The packaging one: setuptools ships `.py` files and nothing else unless told otherwise,
so the corpus was absent from the wheel while every local editable install worked fine.
Testing the config that produces an artefact is not testing the artefact, so the wheel
is built and opened here. Phase H made this worse before it made it better — the corpus
is now a directory of documents *and* a manifest, and a wheel carrying the manifest and
not the documents would install and then fail at plant time.

The behavioural one: with the corpus missing, the v1 runner substituted two stand-in
documents and *completed*. The report then described a 2-document corpus while the config
said thirteen, and nothing on the page disclosed the substitution. That is a setup
problem rendering as a finding, which NF9 forbids.
"""

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from legal_rag_audit.corpora import DEFAULT, CorpusSpecError, available, library_root
from legal_rag_audit.corpora import load as load_library_corpus
from legal_rag_audit.corpus_loader import CorpusError, load_corpus

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- packaging


def test_the_bundled_demo_corpus_is_present_in_the_source_tree():
    assert DEFAULT in available()
    corpus = load_library_corpus(DEFAULT)
    assert corpus.documents and corpus.probes


def test_every_subpackage_is_declared():
    """An explicit `packages` list keeps internal_experiments out of the wheel, and
    silently drops anything new that nobody remembered to add.

    The failure is invisible in development: the package imports fine from the working
    tree and is simply missing from the artefact. Phase B shipped a wheel with no
    `probes`, `score` or `transport` package until this compared the two.
    """
    import tomllib

    declared = set(
        tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "tool"
        ]["setuptools"]["packages"]
    )
    root = REPO_ROOT / "src" / "legal_rag_audit"
    on_disk = {"legal_rag_audit"} | {
        "legal_rag_audit." + str(p.parent.relative_to(root)).replace("/", ".")
        for p in root.rglob("__init__.py")
        if p.parent != root
    }
    assert on_disk <= declared, (
        f"packages on disk but absent from pyproject.toml, so absent from the wheel: "
        f"{sorted(on_disk - declared)}"
    )
    assert declared <= on_disk, (
        f"packages declared but not present: {sorted(declared - on_disk)}"
    )


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
        # No `--wheel`: that builds in-place and reuses ./build/lib, so a file
        # deleted from the source tree can still reach the artefact. The default
        # path builds an sdist first and the wheel from that, in a clean tree —
        # which is what a release does, and the only way this test can mean
        # "the artefact is what ships".
        [sys.executable, "-m", "build", "--outdir", str(tmp_path)],
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

    prefix = f"legal_rag_audit/corpora/library/{DEFAULT}/"
    shipped = {n[len(prefix):] for n in names if n.startswith(prefix)}

    expected = {"corpus.yaml", "README.md"}
    corpus = load_library_corpus(DEFAULT)
    for document in corpus.documents:
        state = "documents/revision/" if document.state == "revision" else "documents/"
        expected.add(state + document.filename)

    missing = sorted(expected - shipped)
    assert not missing, f"wheel is missing corpus files: {missing}"


# ------------------------------------------------------------------------- guardrail


def test_the_bundled_demo_corpus_loads_from_the_installed_location():
    """Read through the library, not through a path a test happens to know.

    The point of the check is that a *shipped* corpus resolves by name — which is what
    `plant` does with no configuration at all, and therefore what the try-it path does.
    """
    corpus = load_library_corpus()
    assert corpus.name == DEFAULT
    assert all(d.body.strip() for d in corpus.documents)
    assert Path(library_root(), DEFAULT).is_dir()


def test_a_corpus_missing_a_document_aborts_and_names_it(tmp_path):
    """The successor to the old partial-install check.

    An incomplete corpus is no longer a missing file among thirteen equals — every
    document fills a declared role, so the diagnosis can say what the absent one was
    *for*, which is the difference between a message an author can act on and one they
    have to come and ask about.
    """
    partial = tmp_path / "partial"
    shutil.copytree(Path(library_root(), DEFAULT), partial)
    (partial / "documents" / "supplier_agreement_v2.txt").unlink()

    with pytest.raises(CorpusSpecError) as excinfo:
        load_library_corpus(str(partial))

    message = str(excinfo.value)
    assert "supplier_agreement_v2.txt" in message
    assert "contradiction pair" in message


def test_a_directory_that_is_not_a_corpus_aborts(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(CorpusSpecError, match="is not a corpus"):
        load_library_corpus(str(empty))


def test_an_unknown_corpus_name_lists_the_ones_that_exist():
    with pytest.raises(CorpusSpecError) as excinfo:
        load_library_corpus("no-such-practice-area")
    assert DEFAULT in str(excinfo.value)


def test_no_corpus_configured_aborts():
    with pytest.raises(CorpusError, match="No corpus configured"):
        load_corpus(None)


def test_custom_corpus_path_must_exist(tmp_path):
    with pytest.raises(CorpusError, match="does not exist"):
        load_corpus(str(tmp_path / "nope"))


def test_empty_custom_corpus_directory_aborts(tmp_path):
    empty = tmp_path / "corpus"
    empty.mkdir()
    with pytest.raises(CorpusError, match="no readable documents"):
        load_corpus(str(empty))


def test_custom_corpus_loads(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "one.txt").write_text("The liability cap is $2,000,000.", encoding="utf-8")
    (d / "two.md").write_text("# Notes\n\nArbitration seat is London.", encoding="utf-8")

    documents = load_corpus(str(d))
    assert [x["filename"] for x in documents] == ["one.txt", "two.md"]
    assert documents[0]["id"] == "one"


def test_empty_document_aborts(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "real.txt").write_text("content", encoding="utf-8")
    (d / "blank.txt").write_text("   \n\n", encoding="utf-8")
    with pytest.raises(CorpusError, match="empty"):
        load_corpus(str(d))


def test_non_utf8_document_aborts(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "binary.txt").write_bytes(b"\xff\xfe\x00\x01 not text")
    with pytest.raises(CorpusError, match="not UTF-8"):
        load_corpus(str(d))


def test_hidden_files_are_skipped(tmp_path):
    """macOS drops .DS_Store into directories; it is not a corpus document."""
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "real.txt").write_text("content", encoding="utf-8")
    (d / ".DS_Store").write_bytes(b"\x00\x01\x02")
    documents = load_corpus(str(d))
    assert [x["filename"] for x in documents] == ["real.txt"]


def test_document_order_is_stable(tmp_path):
    """Scoring is deterministic, so corpus order cannot depend on the filesystem."""
    d = tmp_path / "corpus"
    d.mkdir()
    for name in ("c.txt", "a.txt", "b.txt"):
        (d / name).write_text(f"content of {name}", encoding="utf-8")
    assert [x["filename"] for x in load_corpus(str(d))] == [
        "a.txt",
        "b.txt",
        "c.txt",
    ]


def test_no_module_carries_a_silent_corpus_fallback():
    """The two stand-in documents must not come back, anywhere.

    They lived in runner.py, which Phase B deleted. Scanning the whole package rather
    than one file means moving the code does not move it out of the test's view.
    """
    offenders = []
    for path in (REPO_ROOT / "src" / "legal_rag_audit").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "fallback dummy docs" in source or re.search(
            r"Smith v\. Crown \(2024\).{0,200}capped at", source
        ):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"stand-in corpus documents inlined in: {offenders}"


def test_cli_exits_2_on_a_corpus_problem(tmp_path):
    """A setup problem exits 2 with a diagnosis — not 0, not 1, not a traceback.

    Behavioural rather than a grep over cli.py: the exit code is the contract CI reads,
    and it has to survive the code being rearranged.
    """
    config = tmp_path / "config.yaml"
    config.write_text(
        "target:\n"
        "  name: nowhere\n"
        "  endpoints:\n"
        "    chat: http://127.0.0.1:1/chat\n"
        "    upload: http://127.0.0.1:1/upload\n"
        "corpus:\n"
        "  mode: planted\n",
        encoding="utf-8",
    )
    # A directory that exists and is not a planted corpus. Phase G took the other route
    # away: `mode: existing` no longer reads a path, because §9.1's second configuration
    # probes the target's own index and uploads nothing at all (F25). What is still a
    # corpus problem is being handed a tree with no `base/` in it.
    (tmp_path / "not-planted").mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "legal_rag_audit.cli",
            "generate",
            "-c",
            str(config),
            "--corpus",
            str(tmp_path / "not-planted"),
            "--probes-in",
            str(tmp_path / "probes.jsonl"),
            "-o",
            str(tmp_path / "responses.jsonl"),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    assert result.returncode == 2, (
        f"expected exit 2 for a setup problem, got {result.returncode}\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "responses.jsonl").exists(), (
        "a response file was written despite the corpus failing to resolve"
    )
