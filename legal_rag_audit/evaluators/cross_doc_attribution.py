import re
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class CrossDocAttributionEvaluator:
    """
    Tests whether responses synthesizing information from multiple documents
    explicitly cite the origin document for each claim, rather than merging
    them into an orphaned, unverifiable truth.

    For example, if a response says "The fine is $25,000/day and arbitration
    must commence within 14 days", each fact should explicitly reference its
    source (Statute Alpha and Statute Beta respectively). If the system
    blends them into a single un-attributed paragraph, attribution has failed.

    Detection strategy (deterministic, no LLM):
      - Ask a query that requires pulling facts from multiple known documents.
      - Check that each expected fact appears in the answer.
      - Check that the answer contains explicit attribution markers for each
        source document (document names, identifiers, or inline references).
      - FAIL if facts appear without any attribution to their source.
    """

    def __init__(self):
        pass

    def evaluate(
        self,
        answer: str,
        expected_facts_with_sources: List[Tuple[str, str]],
        citations: List = None,
    ) -> Dict[str, Any]:
        """
        Evaluate cross-document attribution quality.

        Args:
            answer: The system's response text.
            expected_facts_with_sources: List of (fact_canary, source_marker)
                tuples. fact_canary is a phrase that should appear in the
                answer. source_marker is a string that should appear near
                or in the same response to prove attribution (e.g., the
                document name "Statute Alpha" or file reference).
            citations: The citations list from the API response, used as
                a fallback to verify attribution if inline markers are
                absent.

        Returns:
            Result dict with status, attribution analysis per fact.
        """
        if citations is None:
            citations = []

        answer_lower = answer.lower()
        citations_lower = " ".join(str(c).lower() for c in citations)
        # Normalize separators so "statute_alpha.txt" matches "statute alpha"
        citations_normalized = re.sub(r'[_\-.]', ' ', citations_lower)

        failures: List[str] = []
        fact_results: List[Dict[str, Any]] = []

        attributed_count = 0
        found_count = 0

        for fact_canary, source_marker in expected_facts_with_sources:
            fact_found = fact_canary.lower() in answer_lower
            # Check for source attribution in both the answer text and
            # the structured citations list. Normalize separators so that
            # filenames like "statute_alpha.txt" match "statute alpha".
            source_marker_lower = source_marker.lower()
            source_in_answer = source_marker_lower in answer_lower
            source_in_citations = (
                source_marker_lower in citations_lower
                or source_marker_lower in citations_normalized
            )

            attributed = source_in_answer or source_in_citations

            result_entry = {
                "fact": fact_canary,
                "expected_source": source_marker,
                "fact_found": fact_found,
                "source_attributed": attributed,
                "source_in_answer": source_in_answer,
                "source_in_citations": source_in_citations,
            }
            fact_results.append(result_entry)

            if fact_found:
                found_count += 1
                if attributed:
                    attributed_count += 1
                else:
                    failures.append(
                        f"Fact '{fact_canary}' appears in answer but is NOT "
                        f"attributed to '{source_marker}' — orphaned claim"
                    )
            else:
                failures.append(
                    f"Expected fact '{fact_canary}' not found in answer"
                )

        total = len(expected_facts_with_sources)
        attribution_rate = attributed_count / found_count if found_count > 0 else 0.0

        status = "FAIL" if failures else "PASS"

        return {
            "status": status,
            "facts_found": found_count,
            "facts_expected": total,
            "facts_attributed": attributed_count,
            "attribution_rate": round(attribution_rate, 3),
            "details": {
                "per_fact": fact_results,
                "failures": failures,
            } if failures else {
                "per_fact": fact_results,
            }
        }
