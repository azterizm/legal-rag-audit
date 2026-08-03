"""10 — Cross-document attribution (§8.2 #10, Tier 1, adjacency).

One invariant per source document; a question that needs both. Each planted fact must
co-occur with its correct document identifier **within the same sentence**, or in a
citation marker attached to that sentence.

**Why a sentence and not a window.** §20.1 item 1 settled this: a token window is an
arbitrary constant, the same class of problem as a 0.85 similarity threshold, and it would
be argued about for the same reason. A sentence is a structural unit of the output itself.
An answer that states the right figure in one sentence and names the right document in the
next has *mentioned* both; it has not attributed one to the other, and a client relying on
it cannot tell which document to go and read.

**Where the segmenter cannot read the output, the check says so.** §8.2 allows degrading
to Tier 2 in that case. This implementation takes the more conservative half: it reports
`NOT_CAPTURED` with the reason rather than reaching for an instrument, because a Tier 2
fallback would mean the same check produced Tier 1 and Tier 2 results in one run
depending on the shape of each answer, and no reader could be expected to track that.

**An orphaned claim's evidence is the missing source marker, not the fact.** The fact
appeared and was supposed to; what is absent is the attribution. Getting that backwards
would put the correctly-stated figure in an evidence file under a heading saying it should
not have been there.
"""

import re
from typing import Any

from ._common import (
    FAIL,
    NOT_CAPTURED,
    PASS,
    co_occurs,
    normalise,
    present,
    result,
    segmentation_is_unreliable,
    sentences,
)


def _identifier_forms(identifier: str) -> list[str]:
    """The identifier as written, and with filename punctuation opened out.

    `statute_alpha.txt` and `statute alpha` are the same document, and a check that
    matched only one of them would record an orphaned claim against a system that
    attributed correctly in the other form. The extension is dropped before the
    separators are opened out, because `statute alpha txt` matches nothing anybody
    would write.
    """
    forms = [identifier]
    stem = re.sub(r"\.(txt|md|pdf|docx?|json|html?)$", "", identifier, flags=re.IGNORECASE)
    for candidate in (stem, stem.replace("_", " ").replace("-", " ")):
        if normalise(candidate) not in {normalise(f) for f in forms}:
            forms.append(candidate)
    return forms


class CrossDocAttributionEvaluator:
    """Each planted fact beside its own document identifier, by sentence unit."""

    def evaluate(
        self,
        answer: str,
        pairs: list[dict[str, str]],
        citations: list[Any] = (),
    ) -> dict[str, Any]:
        declared = list(pairs or [])

        if segmentation_is_unreliable(answer):
            return result(
                NOT_CAPTURED,
                outcome="segmentation_unreliable",
                reason=(
                    "the answer could not be split into sentence units, so the "
                    "adjacency recipe could not be applied. Reported rather than "
                    "approximated: a token window would be an arbitrary constant "
                    "(§20.1 item 1). Not a pass"
                ),
                units=len(sentences(answer)),
                pairs=len(declared),
            )

        cited = " ".join(str(c) for c in (citations or []))
        rows: list[dict[str, Any]] = []
        missing_facts: list[str] = []
        orphaned_sources: list[str] = []

        for pair in declared:
            fact = pair.get("fact", "")
            identifier = pair.get("identifier", "")
            unit = pair.get("unit", "sentence")

            fact_found = present(answer, fact)
            adjacent = any(
                co_occurs(answer, fact, form, unit)
                for form in _identifier_forms(identifier)
            )
            # A structured citation list is attached to the answer as a whole rather
            # than to a sentence, so it counts only where the target returned exactly
            # the document in question — weaker than an inline marker, and recorded
            # separately so the report can say which kind of attribution it saw.
            in_citations = any(
                present(cited, form) for form in _identifier_forms(identifier)
            )

            attributed = adjacent or (fact_found and in_citations)
            rows.append(
                {
                    "fact": fact,
                    "identifier": identifier,
                    "unit": unit,
                    "fact_found": fact_found,
                    "adjacent_in_answer": adjacent,
                    "in_citations": in_citations,
                    "attributed": attributed,
                }
            )

            if not fact_found:
                missing_facts.append(fact)
            elif not attributed:
                orphaned_sources.append(identifier)

        failed = bool(missing_facts or orphaned_sources)

        return result(
            FAIL if failed else PASS,
            absent=missing_facts + orphaned_sources,
            outcome=(
                "orphaned_claim"
                if orphaned_sources
                else ("fact_absent" if missing_facts else "attributed")
            ),
            per_fact=rows,
            facts_expected=len(declared),
            facts_found=sum(1 for r in rows if r["fact_found"]),
            facts_attributed=sum(1 for r in rows if r["attributed"]),
            units=len(sentences(answer)),
        )
