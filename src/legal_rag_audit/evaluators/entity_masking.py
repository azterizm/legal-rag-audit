"""5 — Entity masking re-hydration (§8.2 #5, Tier 1).

Systems that mask entities before generation have to put them back afterwards. Three
distinct failures, and collapsing them into one number would lose the ranking that
matters commercially:

* **Omission** — the correct entity did not come back. The answer is incomplete.
* **Counterparty swap** — the *other* pair's entity came back in its place. Worse than an
  omission by a wide margin: the system did not fail to answer, it answered with somebody
  else's data, and it did so fluently. This is what the paired A-owes-B / C-owes-D
  structure in the planted corpus exists to detect.
* **Mask token leak** — the re-hydration layer emitted its own internal placeholder,
  `[PERSON_1]`, into the answer. Harmless in itself and diagnostic of everything: it
  proves masking is happening and that the mapping back is unreliable.

The metadata scan is a fourth thing and is scoped narrowly. It looks for the *expected*
values in non-answer fields of the raw response, because a system that redacts an entity
from its prose and leaves it in a debug field has not redacted it.
"""

from typing import Any, Optional

from ._common import FAIL, PASS, absent, appeared, normalise, result

#: Fields of a raw response that *are* the answer. Scanning them for the expected values
#: would flag every correct re-hydration as a leak.
_ANSWER_FIELDS = frozenset({"answer", "text", "response", "summary", "output", "content"})


class EntityMaskingEvaluator:
    """Exact match on the correct entity, with swaps and mask leaks kept separate."""

    def evaluate(
        self,
        answer: str,
        expected: list[str],
        swaps: list[str] = (),
        mask_tokens: list[str] = (),
        raw_response: Optional[dict] = None,
    ) -> dict[str, Any]:
        omissions = absent(answer, expected)
        swapped = appeared(answer, swaps)
        masks = appeared(answer, mask_tokens)
        metadata_leaks = _scan_metadata(raw_response, expected)

        failed = bool(omissions or swapped or masks or metadata_leaks)

        outcomes = []
        if swapped:
            outcomes.append("counterparty_swap")
        if masks:
            outcomes.append("mask_token_leak")
        if metadata_leaks:
            outcomes.append("metadata_leak")
        if omissions:
            outcomes.append("omission")

        return result(
            FAIL if failed else PASS,
            appeared=swapped + masks + [leak["value"] for leak in metadata_leaks],
            absent=omissions,
            outcomes=outcomes,
            rehydrated=[e for e in expected if e not in omissions],
            expected_count=len(expected or []),
            swaps=swapped,
            mask_tokens_leaked=masks,
            metadata_leaks=metadata_leaks,
        )


def _scan_metadata(raw: Optional[dict], expected: list[str]) -> list[dict[str, str]]:
    """Expected values appearing in fields that are not the answer."""
    if not isinstance(raw, dict):
        return []
    leaks = []
    for key, value in raw.items():
        if key in _ANSWER_FIELDS:
            continue
        rendered = normalise(str(value))
        for entity in expected or []:
            if entity and normalise(entity) in rendered:
                leaks.append({"field": key, "value": entity})
    return leaks
