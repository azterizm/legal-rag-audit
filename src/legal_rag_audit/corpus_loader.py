"""Corpus resolution and integrity guardrail.

NF9 — failure is loud. A setup problem must abort with a diagnosis, never degrade into
a finding. Before this module existed, a missing bundled corpus fell through to two
hard-coded stand-in documents and the run *completed*: the report characterised a
2-document corpus while the config said thirteen, and nothing on the page said so.

The bundled corpus is a demo. It exists so somebody can try the harness against a best
case without authoring anything. Real engagements run a domain-specific corpus authored
per target (V2_FULL_PLAN.md §9.4, §9.5), so the guardrail here is about the corpus being
*present and readable*, not about it being right for anyone's jurisdiction.
"""

import os
from typing import Any, Dict, List, Optional

# The bundled demo corpus, by filename. Declared rather than counted so that a partial
# install names the documents it is missing. Each maps to specific facts the evaluators
# assert against, so a subset is not a smaller corpus — it is a broken one.
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


class CorpusError(Exception):
    """A corpus setup problem. Aborts the run; never becomes a finding."""


def bundled_corpus_path() -> str:
    return os.path.join(os.path.dirname(__file__), "corpus")


def _read_documents(corpus_path: str) -> List[Dict[str, str]]:
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


def _check_bundled_complete(corpus_path: str, documents: List[Dict[str, str]]) -> None:
    present = {d["filename"] for d in documents}
    missing = [name for name in BUNDLED_DOCUMENTS if name not in present]
    if not missing:
        return
    raise CorpusError(
        f"The bundled demo corpus is incomplete at {corpus_path}\n"
        f"  expected {len(BUNDLED_DOCUMENTS)} documents, found {len(present)}\n"
        f"  missing: {', '.join(missing)}\n"
        f"Each bundled document carries facts the evaluators assert against, so a "
        f"partial corpus produces findings that describe the corpus rather than the "
        f"target. If this package was installed from a wheel, the wheel was built "
        f"without its package data."
    )


def load_corpus(
    use_bundled: bool, path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Resolve and read the corpus, or raise CorpusError with a diagnosis.

    Never returns an empty list and never substitutes stand-in documents.
    """
    if use_bundled:
        corpus_path = bundled_corpus_path()
        if not os.path.isdir(corpus_path):
            raise CorpusError(
                f"corpus.use_bundled is set, but the bundled corpus is not installed.\n"
                f"  expected at: {corpus_path}\n"
                f"This means the package was built without its corpus data. Reinstall "
                f"from a wheel built with package-data, install in editable mode "
                f"(pip install -e .), or set corpus.path to your own directory."
            )
        documents = _read_documents(corpus_path)
        _check_bundled_complete(corpus_path, documents)
        return documents

    if not path:
        raise CorpusError(
            "No corpus configured. Set corpus.use_bundled to true for the bundled "
            "demo corpus, or corpus.path to a directory of text or markdown documents."
        )

    if not os.path.isdir(path):
        raise CorpusError(
            f"corpus.path does not exist or is not a directory: {path}"
        )

    documents = _read_documents(path)
    if not documents:
        raise CorpusError(
            f"corpus.path contains no readable documents: {path}\n"
            f"Expected text or markdown files. The corpus is the ground truth; without "
            f"it every check would score against nothing."
        )
    return documents
