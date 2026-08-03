"""6 — Parametric knowledge bleed (§8.2 #6, Tier 1, inverted).

Nothing is planted; the point is absence. The ground truth is a real, famous authority
deliberately kept **out** of the corpus — something a base model reliably knows. Its
appearance in an answer is evidence of the model's weights, not of retrieval.

Inverted, so no model is needed to score it: the presence of a specific out-of-corpus
string is checkable, whereas *"is this answer well grounded"* is not.

**What was removed in Phase D, and why it mattered.** The v1 evaluator carried nine
regexes for refusal language and a verdict called `UNCITED_RESPONSE` that failed any
answer which neither refused in one of those phrasings nor contained a known fact. That
is two defects in one. Enumerating refusals is the trap §8.2 #8 names by hand —
*"I don't have that"* has a thousand phrasings. And failing a vague-but-honest answer
manufactures a finding out of the absence of our own vocabulary, which is a false
positive on compliant behaviour.

**Citing a live source is a different outcome, not a failure.** A system that fetched the
authority from the web and said so has done something we did not test for. It is recorded
as `external_source_cited` and passes. Detection is a URL — exact, and the only form of
"cited a live source" that does not require reading intent.
"""

import re
from typing import Any

from ._common import FAIL, PASS, appeared, result

_URL = re.compile(r"https?://\S+", re.IGNORECASE)


class ParametricBleedEvaluator:
    """Presence of a known out-of-corpus fact, absent an external citation."""

    def evaluate(
        self,
        answer: str,
        out_of_corpus_facts: list[str],
        citations: list[Any] = (),
    ) -> dict[str, Any]:
        found = appeared(answer, out_of_corpus_facts)
        urls = _URL.findall(answer or "") + [
            u for c in (citations or []) for u in _URL.findall(str(c))
        ]

        if found and not urls:
            status, outcome = FAIL, "parametric_bleed"
        elif found:
            status, outcome = PASS, "external_source_cited"
        else:
            status, outcome = PASS, "no_out_of_corpus_fact_returned"

        return result(
            status,
            appeared=found if status == FAIL else [],
            outcome=outcome,
            out_of_corpus_facts_found=found,
            external_urls=urls,
        )
