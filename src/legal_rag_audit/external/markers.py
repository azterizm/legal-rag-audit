"""Publisher editorial markers (§8.2 #18, F43, §20.1 item 7).

*"Do you hold rights to all content in your index?"* is a standard TPRM question and one
of the very few where a diagnostic can return evidence instead of a policy answer.
Commercial legal publishers licence **access** — per seat, per query, through their own
interface. Bulk ingestion of the licensed edition into a vendor's own vector index is a
different act, and it is the act a RAG build most naturally performs. So the check turns
on **where the content lives**, not on whether it was ever lawfully read.

The ground truth is the **editorial layer**: a judgment is public, and what the publisher
adds to it is the licensed asset. §8.2 names two classes of it, and this file ships one.

**Proprietary identifiers — shipped.** Publisher-assigned strings that appear nowhere in
the primary source. Reproducing one in our report is not a reproduction of protected
expression, so they can sit in this repository, be published, and be quoted in a finding.

**Editorial prose — not shipped, and deliberately.** Headnotes, synopses and annotations
are the protected expression itself. §20.1 item 7 settles the question this raises: we
would have to hold the licence to store what we are asking somebody else about. Where a
paid engagement warrants it, the method is shingle hashing so no licensed text is stored
and at most a short excerpt is quoted. **Never bulk-store a publisher's editorial layer
to test whether someone else has.**

**Two identifier classes are specified and not scored, for the same reason citation
counter (b) is not.** Star pagination (`*1207`) and the KeyCite / Shepard's signal marks
are genuine markers, and both can be reached innocently: a system emitting `*1207*` as
emphasis around a page number, or the words *yellow flag* in an unrelated sentence, would
be recorded as serving licensed content. §14.2 makes a false positive a release blocker,
and this is the check where one alleges unlawful conduct by a named company (§16.3). The
result says they were not scored rather than omitting them.
"""

import re
from dataclasses import dataclass
from typing import Any, Final, Optional


@dataclass(frozen=True)
class MarkerClass:
    """One family of publisher-assigned identifiers."""

    name: str
    publisher: str
    pattern: re.Pattern
    #: What it is, in a sentence a procurement reviewer can read.
    describes: str


#: Every pattern is anchored on a publisher-assigned token that does not occur in the
#: primary source. None of them matches a neutral citation — `[2019] EWCA Civ 1` is a
#: court-assigned identifier that anyone may quote, and a rule that caught it would fire
#: on every system that cites case law correctly.
MARKER_CLASSES: Final[tuple[MarkerClass, ...]] = (
    MarkerClass(
        name="westlaw_citation",
        publisher="Thomson Reuters (Westlaw)",
        pattern=re.compile(r"\b\d{4}\s+WL\s+\d{3,9}\b"),
        describes="a Westlaw-assigned document citation",
    ),
    MarkerClass(
        name="lexis_citation",
        publisher="RELX (LexisNexis)",
        pattern=re.compile(
            r"\b\d{4}\s+(?:U\.?S\.?\s+(?:Dist\.?|App\.?)\s+)?LEXIS\s+\d{1,9}\b",
            re.IGNORECASE,
        ),
        describes="a LexisNexis-assigned document citation",
    ),
    MarkerClass(
        name="west_key_number",
        publisher="Thomson Reuters (West)",
        # The digit-k-digit form is West's own topic/key notation and occurs in no
        # primary source. Bounded on both sides so it cannot match an ordinary token.
        pattern=re.compile(r"\b\d{1,3}k\d{2,5}\b"),
        describes="a West Key Number classifying a point of law",
    ),
)

#: Specified in §8.2 #18 and **not scored**, with the reason carried into every result
#: rather than left to a footnote.
NOT_SCORED: Final[dict[str, str]] = {
    "star_pagination": (
        "star pagination (`*1207`) is a genuine publisher marker and is not scored: an "
        "answer that renders a page number in emphasis produces the same characters, "
        "and a false positive on this check alleges unlawful conduct by a named company"
    ),
    "signal_marks": (
        "KeyCite and Shepard's signal marks are not scored: they are ordinary English "
        "words in their textual form, so matching them would fire on sentences that "
        "have nothing to do with a publisher's index"
    ),
}

NOT_SCORED_REASON: Final = (
    "Two marker classes named in §8.2 #18 are specified and not scored. "
    + " ".join(NOT_SCORED.values())
    + ". The editorial-prose class is not shipped at all: storing a publisher's "
    "headnotes in order to test whether somebody else has stored them would be the act "
    "under examination (§20.1 item 7)"
)


@dataclass(frozen=True)
class Hit:
    """One marker found, and where."""

    marker: str
    marker_class: str
    publisher: str
    #: `retrieved_chunks` or `answer`. Which one decides the outcome, so it is never
    #: folded away: a marker in a chunk is their retriever returning it, and a marker in
    #: prose could be several other things.
    where: str
    doc_id: Optional[str] = None

    def to_record(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "marker_class": self.marker_class,
            "publisher": self.publisher,
            "where": self.where,
            "doc_id": self.doc_id,
        }


def find(text: str, where: str, doc_id: Optional[str] = None) -> list[Hit]:
    """Every marker in one piece of text, in marker-class declaration order."""
    hits: list[Hit] = []
    for marker_class in MARKER_CLASSES:
        for match in marker_class.pattern.findall(text or ""):
            value = " ".join(match.split())
            if any(h.marker == value and h.where == where for h in hits):
                continue
            hits.append(
                Hit(
                    marker=value,
                    marker_class=marker_class.name,
                    publisher=marker_class.publisher,
                    where=where,
                    doc_id=doc_id,
                )
            )
    return hits
