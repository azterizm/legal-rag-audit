"""Corpus resolution and integrity guardrail.

NF9 — failure is loud. A setup problem must abort with a diagnosis, never degrade into
a finding. Before this module existed, a missing corpus fell through to two hard-coded
stand-in documents and the run *completed*: the report characterised a 2-document corpus
while the config said thirteen, and nothing on the page said so.

This module reads a **planted** corpus: a directory `plants.pipeline` has already written
values into. What a corpus *is* — which documents, which invariants, which questions —
lives in `corpora/`, and the two are deliberately separate. A planted corpus is written
out and then read back through here, so what gets uploaded is byte-for-byte what `hash`
sealed. Passing the documents in memory would be faster and would mean the sealed tree and
the uploaded tree were two objects nobody had compared.

    <root>/base/       every document in its first state
    <root>/revision/   documents that replace their base counterpart later

**Where the thirteen bundled documents went.** Phase D replaced the hand-written
expectations they carried with seeded plants, which left thirteen files that nothing
loaded and a packaging gate protecting them. Phase H retired them and gave their name to
the corpus that the free run actually uses: `corpora/library/bundled-demo/`, whose
documents carry the same nine roles §9.4 lists and, unlike these, carry ground truth.
Their content is in the history if it is ever wanted.
"""

import os
from typing import Any, Dict, List, Optional

#: Where the two states of a planted corpus live under its root.
BASE = "base"
REVISION = "revision"


class CorpusError(Exception):
    """A corpus setup problem. Aborts the run; never becomes a finding."""


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


def load_corpus(path: Optional[str]) -> List[Dict[str, Any]]:
    """Read a directory of documents, or raise CorpusError with a diagnosis.

    Never returns an empty list and never substitutes stand-in documents.
    """
    if not path:
        raise CorpusError(
            "No corpus configured. Set corpus.mode to `planted` to have one generated "
            "from a seed and a named corpus (see `corpus.library`), or corpus.mode to "
            "`existing` to probe the target's own index and upload nothing."
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
