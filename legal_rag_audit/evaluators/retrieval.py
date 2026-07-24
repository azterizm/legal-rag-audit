import logging
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)

class RetrievalEvaluator:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info(f"Loading embedding model for retrieval evaluation: {model_name}")
        self.model = SentenceTransformer(model_name)

    def evaluate(self, query: str, retrieved_texts: List[str], threshold: float) -> Dict[str, Any]:
        """
        Measures semantic similarity between the query and the retrieved chunks.
        """
        if not retrieved_texts:
            return {
                "status": "FAIL",
                "avg_similarity": 0.0,
                "threshold": threshold,
                "details": "No retrieved chunks to evaluate."
            }
            
        query_emb = self.model.encode(query, convert_to_tensor=True)
        chunk_embs = self.model.encode(retrieved_texts, convert_to_tensor=True)
        
        # Compute cosine similarities between query and all chunks
        cosine_scores = util.cos_sim(query_emb, chunk_embs)[0]
        
        avg_score = cosine_scores.mean().item()
        status = "PASS" if avg_score >= threshold else "FAIL"
        
        return {
            "status": status,
            "avg_similarity": round(avg_score, 3),
            "threshold": threshold
        }
