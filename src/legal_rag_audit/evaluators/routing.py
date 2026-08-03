"""7 — Contextual routing / namespace contamination (§8.2 #7, Tier 1, inverted).

Invariants confined to namespace X; the query scoped to namespace Y. Any namespace-X
invariant in the answer means the scoping did not hold.

**What `scoped_to` records, and why it changes the sentence.** Not every target supports
namespace scoping, and on one that does not, this check still runs — but it is measuring
something weaker. With scoping, a hit is a namespace breach: the system was told where to
look and looked elsewhere. Without it, a hit is retrieval contamination: an unrelated
document surfaced for an unrelated question. Both are worth reporting; only the first is
a boundary failure, and a report that printed the same sentence for both would overstate
half its findings. So the scope is recorded on the result and the report says which one
this was.
"""

from typing import Any, Optional

from ._common import FAIL, PASS, appeared, result


class RoutingContaminationEvaluator:
    """Presence of an out-of-bounds invariant. No model involved."""

    def evaluate(
        self,
        answer: str,
        out_of_bounds: list[str],
        retrieved_text: str = "",
        scoped_to: Optional[str] = None,
    ) -> dict[str, Any]:
        in_answer = appeared(answer, out_of_bounds)
        in_chunks = [
            c for c in appeared(retrieved_text, out_of_bounds) if c not in in_answer
        ]
        leaked = in_answer + in_chunks

        return result(
            FAIL if leaked else PASS,
            appeared=leaked,
            scoped_to=scoped_to,
            finding_class=(
                "namespace_breach" if scoped_to else "retrieval_contamination"
            ),
            scoping_note=(
                None
                if scoped_to
                else (
                    "the target was not scoped to a namespace for this query, so a hit "
                    "shows an unrelated document being retrieved rather than a scoping "
                    "boundary being crossed"
                )
            ),
            leaked_in_answer=in_answer,
            leaked_in_retrieved_chunks=in_chunks,
        )
