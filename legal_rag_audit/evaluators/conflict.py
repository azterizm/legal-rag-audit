import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ContradictionSurfacingEvaluator:
    """Presence check for both sides of a planted contradiction. No model involved."""

    def evaluate(self, answer: str, expected_conflicts: List[str]) -> Dict[str, Any]:
        """
        Evaluates if the system successfully surfaces contradictions.
        """
        answer_lower = answer.lower()
        surfaced_count = 0
        
        for conflict in expected_conflicts:
            if conflict.lower() in answer_lower:
                surfaced_count += 1
                
        # Both planted values present => the conflict was surfaced.
        # Exactly one present => one side was silently picked. §8.2 #9 splits these
        # into distinct outcomes and records which side won; carried to Phase D.
        status = "PASS" if surfaced_count >= len(expected_conflicts) else "FAIL"
        
        return {
            "status": status,
            "surfaced_conflicts": surfaced_count,
            "expected": len(expected_conflicts),
            "details": {
                "message": "Evaluated contradiction surfacing based on expected keywords."
            }
        }
