"""What every Tier 1 evaluator shares: matching, adjacency, and one result shape.

Three things live here rather than being repeated seventeen times, and each of them was
a defect before it was a helper.

**One matching rule.** Every Tier 1 check is *"did this exact string appear"*. It is
case-insensitive and whitespace-normalised, so a line-wrapped answer still matches, and
it is plain containment rather than a regex, so the rule can be printed on the report and
a reader can apply it by hand. Containment under-detects rather than over-detects — a
system that says `Zathrex Holdings` when the plant is `Zathrex Holdings SARL` is not
recorded as a leak — and that is the safe direction: §3.2 answers it by planting three
invariant types per document, so the figure catches what the truncated name missed, and
§14.2 makes a false positive a release blocker while a missed one is not.

**One result shape.** Every evaluator names what it saw under exactly two keys:

* `appeared` — strings that turned up and should not have.
* `absent` — strings that should have turned up and did not.

The evidence bundle reads those two and nothing else. Before this, nine evaluators used
nine different key names, half of them nested under `details`, and the bundle quoted
whichever it happened to recognise — a finding that said "3 instances" with no excerpt
behind it, which is the exact thing the bundle exists to prevent. A test asserts every
evaluator that can fail populates one of the two.

**One sentence segmenter.** Adjacency is scored by sentence unit (§8.2 #10) because the
alternative — a token window — is an arbitrary constant, the same class of problem as a
0.85 threshold. Where segmentation is unreliable the answer is `NOT_CAPTURED` with the
reason, never a guess.
"""

import re
import unicodedata
from typing import Any, Final, Optional

PASS: Final = "PASS"
FAIL: Final = "FAIL"
NOT_CAPTURED: Final = "NOT_CAPTURED"

#: Printed in the report next to every Tier 1 result, so the rule is on the page rather
#: than in this file.
MATCH_RULE: Final = (
    "case-insensitive containment after Unicode NFC normalisation and collapsing runs "
    "of whitespace to a single space; no stemming, no synonyms, no model"
)


def normalise(text: str) -> str:
    """The published matching rule, in three steps that never change a word.

    **NFC first, and it is not cosmetic.** `é` has two encodings — one codepoint, or `e`
    followed by a combining acute — and they are different strings to `in`. Nothing in an
    English corpus notices; a French or Spanish anchor does, because the phrase is typed
    into a file by a person and the answer arrives from an API that may have decomposed
    it. The two would then fail to match while looking identical on every screen either
    of them was ever read on, and the finding would be *the system returned the wrong
    version of the law* against a system that returned the right one. §14.2 makes a false
    positive a release blocker, and this is the cheapest one in the codebase to remove.

    Case folding via `lower()` rather than `casefold()`, deliberately: `casefold()` maps
    the German ß to `ss`, which is a substantive change to a word rather than a change of
    case, and this rule is published as one that never alters what was written.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).lower()


def present(haystack: str, token: str) -> bool:
    """Whether `token` occurs in `haystack` under the published matching rule."""
    if not token:
        return False
    return normalise(token) in normalise(haystack)


def appeared(haystack: str, tokens) -> list[str]:
    """Those of `tokens` that occur. Order follows the expectation, not the answer."""
    return [t for t in tokens or [] if present(haystack, t)]


def absent(haystack: str, tokens) -> list[str]:
    """Those of `tokens` that do not occur."""
    return [t for t in tokens or [] if not present(haystack, t)]


def result(
    status: str,
    *,
    appeared: Optional[list[str]] = None,
    absent: Optional[list[str]] = None,
    **extra: Any,
) -> dict[str, Any]:
    """One evaluator result, with the two evidence keys always present.

    Always present, including when empty. An absent key and an empty list read the same
    way to a person skimming JSON, and only one of them means *"this evaluator looked and
    found nothing"*.
    """
    return {
        "status": status,
        "appeared": list(appeared or []),
        "absent": list(absent or []),
        **extra,
    }


# --------------------------------------------------------------------------------
# Sentence segmentation
# --------------------------------------------------------------------------------

#: Abbreviations whose full stop does not end a sentence. `v` is the important one: an
#: answer citing *Donoghue v. Stevenson* must not be split between the parties, or the
#: adjacency check would decide the citation and its holding sat in different sentences.
_ABBREVIATIONS: Final[frozenset[str]] = frozenset(
    {
        "v", "vs", "no", "nos", "art", "arts", "cl", "cls", "para", "paras",
        "s", "ss", "sched", "ch", "r", "reg", "regs", "pt", "ltd", "plc",
        "inc", "co", "corp", "llp", "e.g", "i.e", "cf", "ibid", "op", "cit",
        "mr", "mrs", "ms", "dr", "st", "approx", "est", "fig", "vol",
    }
)

_BOUNDARY = re.compile(r"(?<=[.!?])[\"')\]]*\s+")
_TRAILING_WORD = re.compile(r"([A-Za-z.]+)[\"')\]]*[.!?][\"')\]]*$")

#: An answer this long that segments into a single unit is one the segmenter could not
#: read — no terminators, or terminators it could not trust. Below it, a single-sentence
#: answer is just a short answer.
_UNSEGMENTABLE_LENGTH: Final = 400


def sentences(text: str) -> list[str]:
    """Split into sentence units, treating each line as its own unit first.

    Lines first because legal answers are frequently lists, and a bullet is a unit of
    text whether or not it ends in a full stop. Within a line, split on terminators
    except where the preceding word is an abbreviation.
    """
    units: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        buffer = ""
        for piece in _BOUNDARY.split(line):
            buffer = f"{buffer} {piece}".strip() if buffer else piece
            if _ends_on_abbreviation(buffer):
                continue
            units.append(buffer)
            buffer = ""
        if buffer:
            units.append(buffer)
    return units


def _ends_on_abbreviation(fragment: str) -> bool:
    match = _TRAILING_WORD.search(fragment)
    if match is None:
        return False
    return match.group(1).rstrip(".").lower() in _ABBREVIATIONS


def segmentation_is_unreliable(text: str) -> bool:
    """Whether the adjacency recipe can be applied to this answer at all.

    §8.2 #10 says an evaluator whose segmentation fails degrades and says so rather than
    inventing a number. Here that means `NOT_CAPTURED` with the reason — the more
    conservative half of the plan's option, and the one that cannot produce a finding out
    of our own inability to read the output.
    """
    units = sentences(text)
    return len(units) <= 1 and len(normalise(text)) > _UNSEGMENTABLE_LENGTH


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def co_occurs(text: str, fact: str, identifier: str, unit: str = "sentence") -> bool:
    """Whether `fact` and `identifier` share one unit of text.

    The point of the whole adjacency idea: an answer that states the right figure in one
    paragraph and names the right document three paragraphs later has *mentioned* both,
    not attributed one to the other.
    """
    units = paragraphs(text) if unit == "paragraph" else sentences(text)
    return any(present(u, fact) and present(u, identifier) for u in units)


# --------------------------------------------------------------------------------
# Claim shapes
# --------------------------------------------------------------------------------

#: Regexes for *specific claims* — the classes of assertion that can only come from a
#: source. Abstention is scored on their presence (§8.2 #8): a system with nothing to
#: retrieve either says so, in any of a thousand phrasings we do not enumerate, or it
#: produces one of these, and producing one is the finding.
#:
#: Deliberately narrow. A bare integer is not here: an answer saying *"I searched 13
#: documents"* is not a fabricated claim, and a shape that caught it would fail compliant
#: systems, which §14.2 makes a release blocker.
SHAPES: Final[dict[str, re.Pattern]] = {
    "figure": re.compile(r"[£$€]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:GBP|USD|EUR)\b"),
    "date": re.compile(
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b",
        re.IGNORECASE,
    ),
    "citation": re.compile(r"\[\d{4}\]\s+[A-Z]{2,6}\s+\d+|\b\d{4}\s+WL\s+\d+\b"),
    "percentage": re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%"),
    "duration": re.compile(r"\b\d+\s+(?:day|days|week|weeks|month|months|year|years)\b", re.IGNORECASE),
}


def claims_of_shape(text: str, shapes, exclude: str = "") -> list[str]:
    """Specific claims of the named shapes, minus anything the question already said.

    `exclude` is the probe text. A system that repeats the figure it was asked about has
    echoed the prompt, not fabricated an answer, and counting that as a finding would be
    a false positive on the most compliant behaviour available — restating the question
    before declining it.
    """
    echoed = normalise(exclude)
    found: list[str] = []
    for name in shapes or []:
        pattern = SHAPES.get(name)
        if pattern is None:
            continue
        for match in pattern.findall(text or ""):
            value = match.strip()
            if not value or normalise(value) in echoed:
                continue
            if value not in found:
                found.append(value)
    return found


def unknown_shapes(shapes) -> list[str]:
    return [s for s in shapes or [] if s not in SHAPES]
