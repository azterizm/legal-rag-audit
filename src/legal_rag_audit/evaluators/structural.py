"""12 — Structural integrity, i.e. chunking (§8.2 #12, Tier 1).

An invariant planted deep inside a nested list, whose meaning depends on a heading
several levels above it; a second invariant planted in that heading. The question is
relational — it connects the heading to the leaf. The answer must contain the leaf **and
associate it with the correct heading**, which is scored by adjacency, not by both strings
being present somewhere.

That distinction is the check. Naive fixed-size chunking severs a heading from its
sub-items, and the symptom is precisely an answer that has the figure and cannot say which
band it belongs to — or, worse, attaches it to the wrong one. A decoy figure sits at the
same leaf position under a different heading so that "the wrong one" is detectable rather
than merely suspected.

Where the answer cannot be split into units the adjacency recipe is not applied and the
record is `NOT_CAPTURED`, for the reason set out in `cross_doc_attribution`.
"""

from typing import Any

from ._common import (
    FAIL,
    NOT_CAPTURED,
    PASS,
    absent,
    appeared,
    co_occurs,
    result,
    segmentation_is_unreliable,
    sentences,
)


class StructuralIntegrityEvaluator:
    """Leaf invariant beside its heading; decoys from the wrong branch flagged."""

    def evaluate(
        self,
        answer: str,
        required: list[str],
        forbidden: list[str] = (),
        pairs: list[dict[str, str]] = (),
    ) -> dict[str, Any]:
        declared = list(pairs or [])

        if declared and segmentation_is_unreliable(answer):
            return result(
                NOT_CAPTURED,
                outcome="segmentation_unreliable",
                reason=(
                    "the answer could not be split into units, so the heading-to-leaf "
                    "association could not be scored. Presence alone is not the check: "
                    "an answer holding both strings in unrelated places is what severed "
                    "chunking looks like. Not a pass"
                ),
                units=len(sentences(answer)),
            )

        missing = absent(answer, required)
        conflated = appeared(answer, forbidden)

        unattached: list[str] = []
        rows: list[dict[str, Any]] = []
        for pair in declared:
            fact = pair.get("fact", "")
            identifier = pair.get("identifier", "")
            unit = pair.get("unit", "sentence")
            adjacent = co_occurs(answer, fact, identifier, unit)
            rows.append(
                {
                    "fact": fact,
                    "identifier": identifier,
                    "unit": unit,
                    "fact_found": fact not in missing,
                    "associated": adjacent,
                }
            )
            if fact not in missing and not adjacent:
                unattached.append(identifier)

        failed = bool(missing or conflated or unattached)
        if conflated:
            outcome = "wrong_branch"
        elif unattached:
            outcome = "leaf_severed_from_heading"
        elif missing:
            outcome = "leaf_absent"
        else:
            outcome = "structure_preserved"

        return result(
            FAIL if failed else PASS,
            appeared=conflated,
            absent=missing + unattached,
            outcome=outcome,
            per_pair=rows,
            facts_required=len(required or []),
            units=len(sentences(answer)),
        )
