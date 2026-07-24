import logging
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)

class ConfidenceEvaluator:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info(f"Loading embedding model for confidence evaluation: {model_name}")
        self.model = SentenceTransformer(model_name)
        
        # Canonical phrases representing a refusal to answer due to lack of context
        self.canonical_refusals = [
            "I do not have enough information to answer that question.",
            "The provided documents do not contain the answer.",
            "I cannot answer this based on the available context.",
            "There is insufficient information to provide a reliable answer.",
            "I don't have that information in the materials available to me."
        ]
        # Pre-compute embeddings for canonical refusals
        self.canonical_embs = self.model.encode(self.canonical_refusals, convert_to_tensor=True)

    def evaluate(self, answer: str, threshold: float = 0.5) -> Dict[str, Any]:
        """
        Evaluates if the system correctly refused to answer a query 
        by measuring semantic similarity between the answer and canonical refusal phrases.
        """
        if not answer:
            return {
                "status": "FAIL",
                "refused_correctly": False,
                "max_similarity": 0.0,
                "threshold": threshold,
                "details": "Model attempted to answer without context or provided empty answer."
            }
            
        answer_emb = self.model.encode(answer, convert_to_tensor=True)
        
        # Calculate cosine similarity with all canonical refusals
        cosine_scores = util.cos_sim(answer_emb, self.canonical_embs)[0]
        
        # We take the maximum similarity score to any of the refusal phrases
        max_score = cosine_scores.max().item()
        
        refused_correctly = bool(max_score >= threshold)
        status = "PASS" if refused_correctly else "FAIL"
        
        return {
            "status": status,
            "refused_correctly": refused_correctly,
            "max_similarity": round(max_score, 3),
            "threshold": threshold,
            "details": "Model attempted to answer without context." if not refused_correctly else "Model correctly refused."
        }
