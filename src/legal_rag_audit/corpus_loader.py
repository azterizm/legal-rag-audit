"""Corpus resolution and integrity guardrail.

NF9 — failure is loud. A setup problem must abort with a diagnosis, never degrade into
a finding. Before this module existed, a missing corpus fell through to two hard-coded
stand-in documents and the run *completed*: the report characterised a 2-document corpus
while the config said thirteen, and nothing on the page said so.

Two shapes of corpus, and the reader below handles both the same way once they are on
disk — which is deliberate. A planted corpus is written out by `plants.pipeline` and then
read back through this module, so what gets uploaded is byte-for-byte what `hash` sealed.
Passing the documents in memory would be faster and would mean the sealed tree and the
uploaded tree were two objects nobody had compared.

    <root>/base/       every document in its first state
    <root>/revision/   documents that replace their base counterpart later

The bundled thirteen-document set is still shipped and still checked for completeness by
`tests/test_corpus_packaging.py`. Nothing selects it automatically any more: Phase D
replaced the hand-written expectations it carried with seeded plants, and §9.4 gives Phase
H the job of deciding what it becomes. Until then it is reachable by pointing
`corpus.path` at `bundled_corpus_path()`.
"""

import os
from typing import Any, Dict, List, Optional

# The bundled demo corpus, by filename. Declared rather than counted so that a partial
# install names the documents it is missing.
BUNDLED_DOCUMENTS = (
    "adversarial_injection.txt",
    "case_01_smith_v_crown.txt",
    "case_02_jones_v_state.txt",
    "case_03_doe_v_megacorp.txt",
    "fake_statute_reference.txt",
    "pii_employee_record.txt",
    "reg_finance_404.md",
    "saas_agreement_v1.txt",
    "saas_agreement_v2.txt",
    "statute_alpha.txt",
    "statute_beta.txt",
    "tenant_a_matter.txt",
    "tenant_b_matter.txt",
)

#: Where the two states of a planted corpus live under its root.
BASE = "base"
REVISION = "revision"


class CorpusError(Exception):
    """A corpus setup problem. Aborts the run; never becomes a finding."""


def bundled_corpus_path() -> str:
    return os.path.join(os.path.dirname(__file__), "corpus")


def read_documents(corpus_path: str) -> List[Dict[str, str]]:
    """Every readable document in a directory, in filename order."""
    documents = []
    for filename in sorted(os.listdir(corpus_path)):
        if filename.startswith("."):
            continue
        filepath = os.path.join(corpus_path, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError as e:
            raise CorpusError(
                f"Corpus document is not UTF-8 text: {filepath}\n"
                f"  {e}\n"
                f"The corpus is used verbatim as ground truth, so it must be text."
            ) from e
        if not content.strip():
            raise CorpusError(
                f"Corpus document is empty: {filepath}\n"
                f"An empty document contributes no ground truth and would score every "
                f"claim against it as unsupported."
            )
        documents.append(
            {"id": filename.rsplit(".", 1)[0], "filename": filename, "content": content}
        )
    return documents


def check_bundled_complete(corpus_path: Optional[str] = None) -> None:
    """Refuse a partial install of the bundled set, naming what is missing."""
    corpus_path = corpus_path or bundled_corpus_path()
    if not os.path.isdir(corpus_path):
        raise CorpusError(
            f"The bundled demo corpus is not installed.\n"
            f"  expected at: {corpus_path}\n"
            f"This means the package was built without its corpus data. Reinstall from "
            f"a wheel built with package-data, or install in editable mode "
            f"(pip install -e .)."
        )
    present = {d["filename"] for d in read_documents(corpus_path)}
    missing = [name for name in BUNDLED_DOCUMENTS if name not in present]
    if not missing:
        return
    raise CorpusError(
        f"The bundled demo corpus is incomplete at {corpus_path}\n"
        f"  expected {len(BUNDLED_DOCUMENTS)} documents, found {len(present)}\n"
        f"  missing: {', '.join(missing)}\n"
        f"If this package was installed from a wheel, the wheel was built without its "
        f"package data."
    )


def load_corpus(path: Optional[str]) -> List[Dict[str, Any]]:
    """Read a directory of documents, or raise CorpusError with a diagnosis.

    Never returns an empty list and never substitutes stand-in documents.
    """
    if not path:
        raise CorpusError(
            "No corpus configured. Set corpus.mode to `planted` to have one generated "
            "from a seed, or corpus.path to a directory of text or markdown documents."
        )

    if not os.path.isdir(path):
        raise CorpusError(f"corpus path does not exist or is not a directory: {path}")

    documents = read_documents(path)
    if not documents:
        raise CorpusError(
            f"corpus path contains no readable documents: {path}\n"
            f"Expected text or markdown files. The corpus is the ground truth; without "
            f"it every check would score against nothing."
        )
    return documents


def load_planted(root: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """The two states of a planted corpus: what to upload first, and what replaces it.

    A root with no `base/` is refused rather than treated as a flat directory. The two
    layouts mean different things — a flat directory is a corpus, a planted root is a
    corpus *and a revision of it* — and reading one as the other would silently drop the
    second phase, taking index freshness with it.
    """
    base = os.path.join(root, BASE)
    if not os.path.isdir(base):
        raise CorpusError(
            f"{root} is not a planted corpus: no `{BASE}/` directory.\n"
            f"  A planted corpus is written by `legal-rag-audit plant` and holds\n"
            f"    {root}/{BASE}/       the documents uploaded first\n"
            f"    {root}/{REVISION}/   the documents that replace them later\n"
            f"  If this is an ordinary directory of documents, set corpus.mode to "
            f"`existing`."
        )

    documents = load_corpus(base)
    revision_path = os.path.join(root, REVISION)
    revisions = (
        read_documents(revision_path) if os.path.isdir(revision_path) else []
    )
    return documents, revisions
