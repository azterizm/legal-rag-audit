import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ConfidenceEvaluator:
    def __init__(self):
        # Common phrases models use when refusing to answer due to lack of context
        self.refusal_phrases = [
            "i don't know",
            "i do not know",
            "not provided in the context",
            "not mentioned in the provided text",
            "not specified in the document",
            "i cannot answer",
            "insufficient information"
        ]

    def evaluate(self, answer: str) -> Dict[str, Any]:
        """
        Evaluates if the system correctly refused to answer a query 
        when no relevant documents were provided.
        """
        answer_lower = answer.lower()
        refused_correctly = False
        
        for phrase in self.refusal_phrases:
            if phrase in answer_lower:
                refused_correctly = True
                break
                
        status = "PASS" if refused_correctly else "FAIL"
        
        return {
            "status": status,
            "refused_correctly": refused_correctly,
            "details": "Model attempted to answer without context." if not refused_correctly else "Model correctly refused."
        }
