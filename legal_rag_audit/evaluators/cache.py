import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CacheInvalidationEvaluator:
    def __init__(self):
        pass

    def evaluate(self, answer: str, stale_fact: str, fresh_fact: str) -> Dict[str, Any]:
        """
        Evaluates if the system retrieved the fresh updated index instead of stale cache.
        """
        answer_lower = answer.lower()
        
        has_stale = stale_fact.lower() in answer_lower
        has_fresh = fresh_fact.lower() in answer_lower
        
        if has_fresh and not has_stale:
            status = "PASS"
        else:
            status = "FAIL"
        
        return {
            "status": status,
            "has_stale_data": has_stale,
            "has_fresh_data": has_fresh
        }
