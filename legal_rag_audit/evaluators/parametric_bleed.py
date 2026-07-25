import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ParametricBleedEvaluator:
    """
    Tests whether the RAG system substitutes un-cited pre-trained "world
    knowledge" when the corpus contains no relevant documents for a query.

    A well-built legal RAG system should either:
      (a) Refuse to answer / explicitly flag low confidence, OR
      (b) Explicitly cite an external source (if web search is enabled).

    It must NEVER silently answer from parametric memory (the LLM's
    training data) without any citation — that's the "parametric bleed"
    failure mode.

    Detection strategy (deterministic, no LLM):
      - Send a query about a topic NOT in the corpus.
      - Check if the answer contains a known correct fact (proving it came
        from parametric memory rather than retrieval).
      - Check if the answer contains a refusal / low-confidence signal.
      - Check if the answer contains an explicit external citation.
      - FAIL if it answered correctly from parametric memory without
        citing any source.
    """

    def __init__(self):
        # Common refusal / low-confidence patterns
        self.refusal_patterns = [
            r"(?:i\s+)?(?:do\s+not|don'?t|cannot|can'?t)\s+(?:have|find|locate|provide|answer)",
            r"(?:no|not\s+enough)\s+(?:relevant\s+)?(?:information|data|documents?|context)",
            r"(?:unable|insufficient)\s+(?:to\s+answer|information|context|data)",
            r"(?:outside|beyond)\s+(?:the\s+)?(?:scope|available\s+(?:context|documents?))",
            r"not\s+(?:covered|addressed|found|available)\s+(?:in|within)",
            r"(?:i\s+)?(?:couldn'?t|could\s+not)\s+find",
            r"no\s+(?:matching|relevant)\s+(?:results?|documents?|sources?)",
            r"this\s+(?:topic|question|subject)\s+is\s+not",
            r"based\s+on\s+(?:the\s+)?(?:available|provided)\s+(?:documents?|context|information)",
        ]

        # Patterns indicating an explicit external source citation
        self.external_citation_patterns = [
            r"(?:according\s+to|source[d]?\s+from|retrieved\s+from|reference[d]?)\s+(?:an?\s+)?(?:external|web|internet|online)",
            r"https?://",
            r"(?:wikipedia|web\s+search|external\s+source|external\s+reference)",
        ]

    def evaluate(
        self,
        answer: str,
        parametric_canaries: List[str],
        citations: List = None,
    ) -> Dict[str, Any]:
        """
        Evaluate parametric knowledge bleed.

        Args:
            answer: The system's response text.
            parametric_canaries: Known correct facts for the out-of-corpus
                query that would ONLY be known from the LLM's training data.
                If these appear in the answer WITHOUT an external citation,
                it's a bleed. Case-insensitive matching.
            citations: List of citations returned by the system. If non-empty
                and the answer contains canaries, we check whether the
                citations are plausibly external sources.

        Returns:
            Result dict with status, bleed detection, and refusal analysis.
        """
        if citations is None:
            citations = []

        answer_lower = answer.lower()
        failures: List[str] = []

        # --- Check for refusal signals ---
        refused = False
        matched_refusal = None
        for pattern in self.refusal_patterns:
            match = re.search(pattern, answer_lower)
            if match:
                refused = True
                matched_refusal = match.group(0)
                break

        # --- Check for parametric canary presence ---
        found_canaries = [c for c in parametric_canaries if c.lower() in answer_lower]

        # --- Check for external citation ---
        has_external_citation = False
        for pattern in self.external_citation_patterns:
            if re.search(pattern, answer_lower):
                has_external_citation = True
                break
        # Also check the citations list for URLs or external markers
        if citations:
            for cit in citations:
                cit_str = str(cit).lower()
                if "http" in cit_str or "external" in cit_str:
                    has_external_citation = True
                    break

        # --- Determine verdict ---
        if refused and not found_canaries:
            # System correctly refused to answer
            verdict = "REFUSED_CORRECTLY"
        elif found_canaries and has_external_citation:
            # System answered from external source and cited it — acceptable
            verdict = "EXTERNAL_CITATION"
        elif found_canaries and not has_external_citation:
            # System used parametric memory without citing a source — BLEED
            verdict = "PARAMETRIC_BLEED"
            failures.append(
                f"System answered with parametric knowledge "
                f"({found_canaries}) without citing any external source"
            )
        elif not found_canaries and not refused:
            # System gave some answer but didn't use known parametric facts
            # and didn't refuse — ambiguous but not necessarily a fail.
            # Could be hallucinating something else or giving a vague answer.
            # We check if any citations were provided at all.
            if not citations:
                verdict = "UNCITED_RESPONSE"
                failures.append(
                    "System provided an answer without refusal, without "
                    "matching parametric knowledge, and without any citations"
                )
            else:
                verdict = "CITED_RESPONSE"
        else:
            verdict = "UNKNOWN"

        status = "FAIL" if failures else "PASS"

        return {
            "status": status,
            "verdict": verdict,
            "refused": refused,
            "parametric_canaries_found": len(found_canaries),
            "has_external_citation": has_external_citation,
            "details": {
                "found_canaries": found_canaries,
                "matched_refusal": matched_refusal,
                "failures": failures,
            } if failures else {
                "matched_refusal": matched_refusal,
                "found_canaries": found_canaries,
            }
        }
