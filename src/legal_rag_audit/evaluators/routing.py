import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RoutingContaminationEvaluator:
    def __init__(self):
        pass

    def evaluate(self, answer: str, out_of_bounds_keywords: list) -> Dict[str, Any]:
        """
        Evaluates if the system leaked generic platform knowledge instead of 
        staying within the uploaded corpus namespace.
        """
        answer_lower = answer.lower()
        leaked_keywords = [kw for kw in out_of_bounds_keywords if kw.lower() in answer_lower]
        
        status = "FAIL" if leaked_keywords else "PASS"
        
        return {
            "status": status,
            "leaked_count": len(leaked_keywords),
            "details": {
                "leaked_keywords": leaked_keywords
            } if leaked_keywords else {}
        }
