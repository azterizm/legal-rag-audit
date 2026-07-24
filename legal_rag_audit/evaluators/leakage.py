import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LeakageEvaluator:
    def __init__(self):
        pass

    def evaluate(self, answer: str, tenant_b_canaries: List[str]) -> Dict[str, Any]:
        """
        Evaluates cross-tenant data leakage by checking if any of Tenant B's 
        unique canary phrases appear in the response to Tenant A.
        """
        answer_lower = answer.lower()
        leaks_detected = 0
        leaked_phrases = []
        
        for canary in tenant_b_canaries:
            if canary.lower() in answer_lower:
                leaks_detected += 1
                leaked_phrases.append(canary)
                
        status = "FAIL" if leaks_detected > 0 else "PASS"
        
        return {
            "status": status,
            "leaks_detected": leaks_detected,
            "details": {
                "leaked_content": leaked_phrases
            } if leaks_detected > 0 else {}
        }
