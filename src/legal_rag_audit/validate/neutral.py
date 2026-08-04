"""The neutral probe set, and the neutral document. Hardcoded, on purpose (§7.1).

> **`validate` must not leak the battery.** Neutral throwaway queries only. It must
> never fire real probes or upload the planted corpus — its raw output is printed to
> their terminal, and canaries and injection payloads would be visible in it.

Everything in this file is written to be read by the target's engineer over their own
shoulder. Nothing here is scored, nothing here is an invariant, and nothing here would
tell a reader anything about what the battery asks.

**This is a constant, not an import.** The obvious implementation — take the first three
probes from `probes.battery` and blank their expectations — would put an import edge
from this package to the battery, and from there the only thing standing between a
canary and the target's terminal would be our care in maintaining it. There is no such
edge, and `tests/test_validate.py` walks the module graph to prove it. That is why this
file duplicates the shape of a probe rather than reusing one.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NeutralProbe:
    probe_id: str
    text: str
    #: What this one is here to exercise. Printed beside the result, so the reader can
    #: tell a query that failed to extract from a query that had nothing to extract.
    purpose: str


#: Three, per §7.1. Not one, because a single sample cannot show a latency spread; not
#: ten, because this runs against a system nobody has paid us to touch yet.
NEUTRAL_PROBES: tuple[NeutralProbe, ...] = (
    NeutralProbe(
        probe_id="validate-1",
        text="What is this system for?",
        purpose="the shortest possible round trip — anything at all coming back proves "
        "the endpoint, the auth headers and the request body template",
    ),
    NeutralProbe(
        probe_id="validate-2",
        text=(
            "In two or three sentences, describe the kinds of documents you can "
            "search."
        ),
        purpose="a longer answer, so a stream has something to assemble — a chunk "
        "concatenation that drops frames shows up here and nowhere else",
    ),
    NeutralProbe(
        probe_id="validate-3",
        text="Name up to three documents you can see, with their titles.",
        purpose="an answer that usually carries citations, so the citations JSONPath "
        "is exercised rather than assumed",
    ),
)

#: Uploaded once, to answer the one question in §7.1's table that no query can: whether
#: the upload endpoint hands back an identifier. Citation integrity tests set membership
#: against the identifiers the target issued (§8.2 #2), so an upload that returns 200 and
#: no id silently removes a Tier 1 check — and a run that discovers this at scoring time
#: has already sent the whole corpus.
#:
#: Named so it is obvious in their document list, and worded so whoever finds it next
#: week knows what it is and that deleting it costs nothing.
NEUTRAL_DOCUMENT_FILENAME = "legal-rag-audit-validate.txt"
NEUTRAL_DOCUMENT_ID = "legal-rag-audit-validate"
NEUTRAL_DOCUMENT_TEXT = (
    "This document was uploaded by `legal-rag-audit validate` to check that the "
    "upload endpoint accepts a document and returns an identifier for it.\n"
    "\n"
    "It is not part of any test battery. Nothing in it is scored, nothing in it is "
    "an answer to anything, and it can be deleted at any time.\n"
)
