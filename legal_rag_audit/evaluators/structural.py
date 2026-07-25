import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class StructuralIntegrityEvaluator:
    """
    Tests whether the RAG system correctly handles dense, hierarchically
    structured regulatory documents (nested lists, tables, deep bullet
    points). Naive fixed-size chunking often severs the relationship between
    a header and its sub-items, causing retrieval to return the sub-item
    without its governing header — or vice versa.

    The bundled corpus includes reg_finance_404.md which has:
      - Nested compliance tiers (Tier 1 / Tier 2) with different rules
      - A penalty matrix table linking tiers to fine amounts
      - Deep hierarchical sections (Section → Subsection → list items)

    Detection strategy (deterministic, no LLM):
      - Ask a relational question that requires connecting a parent context
        (e.g., "Tier 2 entity") to a deeply nested fact (e.g., "$250,000
        fine for Material Misstatement").
      - Verify the answer contains ALL required relational facts. If naive
        chunking severed context, the system will either miss facts or
        hallucinate the relationship.
    """

    def __init__(self):
        pass

    def evaluate(
        self,
        answer: str,
        required_relational_facts: List[str],
        forbidden_conflations: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate structural integrity.

        Args:
            answer: The system's response text.
            required_relational_facts: Key phrases that MUST appear to prove
                the system connected the header to its deep sub-items.
                Case-insensitive matching.
            forbidden_conflations: Phrases that MUST NOT appear. These are
                facts from the *wrong* tier/section that would indicate the
                system mixed up hierarchical context.

        Returns:
            Result dict with status, found/missing facts, and conflations.
        """
        if forbidden_conflations is None:
            forbidden_conflations = []

        answer_lower = answer.lower()
        failures: List[str] = []

        # --- Check required relational facts ---
        found_facts = [f for f in required_relational_facts if f.lower() in answer_lower]
        missing_facts = [f for f in required_relational_facts if f.lower() not in answer_lower]

        if missing_facts:
            failures.append(
                f"Missing relational facts (likely due to chunking severing "
                f"header-to-sub-item context): {missing_facts}"
            )

        # --- Check for wrong-tier conflation ---
        conflated = [f for f in forbidden_conflations if f.lower() in answer_lower]

        if conflated:
            failures.append(
                f"Answer conflates facts from wrong hierarchical section: "
                f"{conflated}"
            )

        # --- Compute a coverage score ---
        total = len(required_relational_facts)
        coverage = len(found_facts) / total if total > 0 else 0.0

        status = "FAIL" if failures else "PASS"

        return {
            "status": status,
            "facts_found": len(found_facts),
            "facts_required": total,
            "coverage": round(coverage, 3),
            "conflations_detected": len(conflated),
            "details": {
                "found_facts": found_facts,
                "missing_facts": missing_facts,
                "conflated_facts": conflated,
                "failures": failures,
            } if failures else {
                "found_facts": found_facts,
            }
        }
