"""Digests over the artefacts of a run, and the recipes that let someone else check.

A hash nobody can independently recompute is decoration. Every value this module
produces is therefore either the plain SHA-256 of a file's bytes — one `shasum`
away — or a tree digest whose recipe is stated in full and reproducible with
standard tools. The recipe strings travel with the values, in the handover record
and in the run manifest, so verification never requires our software.

That constraint is the whole point of §3.6. The pre-commitment protects the auditor
from *"you decided what counted as a failure after you saw the failure"*, and it can
only do that if the client can verify it without trusting the tool that made it.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

ALGORITHM = "sha256"

#: How a file digest is computed. Deliberately the most boring possible answer.
FILE_RECIPE = (
    "sha256 of the file's bytes. Verify with: shasum -a 256 <file> "
    "(or sha256sum <file>)."
)

#: How a directory digest is computed. Long, because a directory has no bytes of its
#: own and every choice in the walk has to be stated: which files are included, how
#: paths are spelled, how they are ordered, and what is hashed at the end.
TREE_RECIPE = (
    "sha256 over a listing of the tree. For every regular file under the root whose "
    "relative path contains no dot-prefixed component, one line of "
    "'<sha256 hex><two spaces><relative POSIX path>\\n'; lines sorted by path as "
    "byte strings (LC_ALL=C); the concatenation hashed. Verify with:\n"
    "  cd <root> && find . -type f -not -path '*/.*' | sed 's|^\\./||' | "
    "LC_ALL=C sort | tr '\\n' '\\0' | xargs -0 shasum -a 256 | shasum -a 256\n"
    "The shell form assumes no newlines in filenames; the tool's own computation "
    "does not."
)

#: How an in-memory object is digested when there is no file to point at.
JSON_RECIPE = (
    "sha256 of json.dumps(obj, sort_keys=True, separators=(',',':'), "
    "ensure_ascii=False) encoded UTF-8."
)


class HashError(Exception):
    """Something that was supposed to be hashed could not be read.

    A setup problem, not a finding (NF9). Nothing downstream should paper over it
    with a null digest — an absent hash and a hash of nothing are different claims.
    """


def digest_bytes(data: bytes) -> str:
    return f"{ALGORITHM}:{hashlib.sha256(data).hexdigest()}"


def hash_file(path: str | Path) -> str:
    """Digest a file's bytes, read in chunks so a large corpus document is fine."""
    p = Path(path)
    h = hashlib.sha256()
    try:
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
    except OSError as e:
        raise HashError(f"Cannot hash {p}: {e}") from None
    return f"{ALGORITHM}:{h.hexdigest()}"


def hash_json(obj: Any) -> str:
    """Digest a Python object by its canonical JSON form.

    Canonical means key-sorted and space-free, so the digest is a property of the
    data rather than of how it happened to be serialised. Used for the findings
    digest (NF2) and for anything else with no file behind it.
    """
    canonical = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return digest_bytes(canonical.encode("utf-8"))


@dataclass(frozen=True)
class TreeHash:
    """A directory digest, plus everything needed to argue about it."""

    digest: str
    files: int
    #: (relative POSIX path, sha256 hex) in the order they were hashed.
    listing: tuple[tuple[str, str], ...]

    def listing_text(self) -> str:
        """The exact bytes that were hashed, so a disagreement can be localised."""
        return "".join(f"{h}  {path}\n" for path, h in self.listing)


def _is_hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)


def hash_tree(root: str | Path) -> TreeHash:
    """Digest a directory as the set of files it contains.

    Dot-prefixed paths are excluded. That is a real decision with a real cost: a
    `.DS_Store` dropped into a corpus directory by macOS would otherwise change the
    digest of a corpus nobody touched, and a pre-commitment that fires on filesystem
    noise trains people to ignore it. The exclusion is stated in TREE_RECIPE rather
    than left for someone to discover from a mismatch.
    """
    base = Path(root)
    if not base.is_dir():
        raise HashError(
            f"{base} is not a directory.\n"
            f"  A corpus hash covers a tree of documents. For a single file, hash "
            f"the file."
        )

    entries: list[tuple[str, str]] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(base)
        if _is_hidden(relative):
            continue
        entries.append((relative.as_posix(), hash_file(path)[len(ALGORITHM) + 1 :]))

    # Sorted as byte strings, matching LC_ALL=C in the published recipe. Python's
    # str comparison is by code point, which agrees with byte order for UTF-8.
    entries.sort(key=lambda row: row[0].encode("utf-8"))

    listing = "".join(f"{h}  {path}\n" for path, h in entries)
    return TreeHash(
        digest=digest_bytes(listing.encode("utf-8")),
        files=len(entries),
        listing=tuple(entries),
    )


def hash_path(path: str | Path) -> tuple[str, str, Optional[int]]:
    """Digest a file or a directory, saying which it was.

    Returns (digest, kind, file count). The kind is carried into the record because
    the two digests are computed differently and a reader checking one with the
    other's recipe would conclude, wrongly, that something had been altered.
    """
    p = Path(path)
    if p.is_dir():
        tree = hash_tree(p)
        return tree.digest, "tree", tree.files
    if p.is_file():
        return hash_file(p), "file", None
    raise HashError(f"Nothing to hash at {p} — no such file or directory.")


def recipe_for(kind: str) -> str:
    return {"file": FILE_RECIPE, "tree": TREE_RECIPE, "json": JSON_RECIPE}[kind]
