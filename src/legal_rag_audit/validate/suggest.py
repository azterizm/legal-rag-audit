"""Candidate JSONPaths, guessed from a response body (§7.1).

> Where extraction returns empty it proposes a candidate path heuristically — walk the
> response tree, offer the longest string field and the first array of objects. **Not
> authoritative**; a starting point so they are not guessing.

The hedge in that last sentence is the design. A confident wrong path is worse than no
path: the operator sets it, extraction starts returning *something*, and the something
is a status message or a request id scored as the system's answer. So this offers a
ranked list rather than a single answer, prints the value it found at each candidate
beside it, and the caller labels the whole section as a guess.

Two heuristics, deliberately dumb:

* **The longest string wins**, because an answer is prose and the fields around it are
  identifiers, model names and timestamps. It breaks on a target that echoes the prompt
  — the echo is often longer than the answer — which is why the sample value is printed.
* **The first array of objects**, in document order, for the citations field. Order
  rather than length: the sources list is usually adjacent to the answer, and a longer
  array further down is more likely to be token log-probs or retrieval debug output.

Keys that are not bare identifiers are quoted in bracket form, so a suggested path can
be pasted into the config and parsed by `jsonpath-ng` without editing.
"""

import re
from dataclasses import dataclass
from typing import Any

#: Enough of the value to recognise it, not so much that the suggestion block becomes
#: the response body again — that is printed above it in full.
SAMPLE = 120

#: Below this a string is an identifier, a status or an enum, not an answer. Set low
#: enough that a genuine one-line answer still surfaces.
MIN_ANSWER_CHARS = 24

#: More than this and the reader is scanning rather than reading. The ranking means the
#: cut falls on the least likely candidates.
MAX_CANDIDATES = 5

_BARE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Candidate:
    path: str
    #: Why this one is being offered, in the reader's terms rather than ours.
    why: str
    sample: str


def _quote(key: str) -> str | None:
    """Bracket form for a key that is not a bare identifier, or None if unquotable.

    A suggestion that does not parse is worse than no suggestion — the operator pastes
    it in and the next thing they see is a stack trace from our own config loader. So a
    key holding both quote characters is dropped rather than emitted broken.
    """
    if "'" not in key:
        return f"['{key}']"
    if '"' not in key:
        return f'["{key}"]'
    return None


def _join(prefix: str, key: str) -> str | None:
    if _BARE.match(key):
        return f"{prefix}.{key}" if prefix else key
    piece = _quote(key)
    if piece is None:
        return None
    return f"{prefix}{piece}" if prefix else piece


def _clip(value: str) -> str:
    flat = " ".join(value.split())
    return flat if len(flat) <= SAMPLE else flat[:SAMPLE] + "…"


def _walk(node: Any, prefix: str, strings: list, arrays: list, depth: int) -> None:
    # A body deep enough to need this is a body we are guessing wrong about anyway, and
    # an unbounded walk over a hostile response is an easy way to hang the one command
    # that exists to stop things hanging.
    if depth > 8:
        return

    if isinstance(node, dict):
        for key, value in node.items():
            path = _join(prefix, str(key))
            if path is None:
                continue
            if isinstance(value, str):
                if len(value.strip()) >= MIN_ANSWER_CHARS:
                    strings.append((len(value), path, value))
            elif isinstance(value, list):
                if value and all(isinstance(item, dict) for item in value):
                    arrays.append((path, value))
                elif value and all(isinstance(item, str) for item in value):
                    arrays.append((path, value))
                _walk(value, path, strings, arrays, depth + 1)
            elif isinstance(value, dict):
                _walk(value, path, strings, arrays, depth + 1)
    elif isinstance(node, list):
        # Only the first element. A hundred-element array of identical shapes produces a
        # hundred identical suggestions differing in an index nobody wants.
        for index, item in enumerate(node[:1]):
            _walk(item, f"{prefix}[{index}]", strings, arrays, depth + 1)


def answer_candidates(body: Any) -> list[Candidate]:
    """Paths that might hold the answer, longest string first."""
    strings: list[tuple[int, str, str]] = []
    arrays: list[tuple[str, Any]] = []
    _walk(body, "", strings, arrays, 0)

    # Sorted by length descending, then by path, so the same body always produces the
    # same suggestion — an operator comparing two runs should not have to wonder whether
    # the order meant something.
    strings.sort(key=lambda item: (-item[0], item[1]))

    out = []
    for length, path, value in strings[:MAX_CANDIDATES]:
        out.append(
            Candidate(
                path=path,
                why=f"the longest string in the body ({length} characters)"
                if not out
                else f"a string field ({length} characters)",
                sample=_clip(value),
            )
        )
    return out


def citation_candidates(body: Any) -> list[Candidate]:
    """Paths that might hold the citations, in document order."""
    strings: list[tuple[int, str, str]] = []
    arrays: list[tuple[str, Any]] = []
    _walk(body, "", strings, arrays, 0)

    out = []
    for path, value in arrays[:MAX_CANDIDATES]:
        shape = (
            "objects" if value and isinstance(value[0], dict) else "strings"
        )
        first = value[0]
        sample = _clip(
            ", ".join(sorted(first.keys())) if isinstance(first, dict) else str(first)
        )
        out.append(
            Candidate(
                path=path,
                why=f"a list of {len(value)} {shape}",
                sample=(
                    f"keys: {sample}" if shape == "objects" else f"first: {sample}"
                ),
            )
        )
    return out
