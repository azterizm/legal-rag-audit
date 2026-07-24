import logging
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)

class RetrievalEvaluator:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", use_gemini: bool = False):
        self.use_gemini = use_gemini
        if not use_gemini:
            logger.info(f"Loading embedding model for retrieval evaluation: {model_name}")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
        else:
            logger.info("Using Gemini API for Retrieval evaluation.")

    def _evaluate_with_gemini(self, query: str, retrieved_texts: List[str], threshold: float) -> Dict[str, Any]:
        import os
        import json
        import requests
        import math
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY environment variable not set.")
            return {"status": "ERROR", "avg_similarity": 0.0, "threshold": threshold, "details": "Missing GEMINI_API_KEY"}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents?key={api_key}"
        
        # We need to embed the query and all chunks.
        texts_to_embed = [query] + retrieved_texts
        requests_payload = [{"model": "models/text-embedding-004", "content": {"parts": [{"text": text}]}} for text in texts_to_embed]
        
        try:
            payload = {"requests": requests_payload}
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            
            embeddings_data = resp.json().get("embeddings", [])
            embeddings = [emb["values"] for emb in embeddings_data]
            
            if len(embeddings) != len(texts_to_embed):
                raise ValueError("Mismatch in returned embeddings count.")
                
            query_emb = embeddings[0]
            chunk_embs = embeddings[1:]
            
            def cosine_sim(a, b):
                dot = sum(x*y for x, y in zip(a, b))
                norm_a = math.sqrt(sum(x*x for x in a))
                norm_b = math.sqrt(sum(x*x for x in b))
                if norm_a == 0 or norm_b == 0: return 0.0
                return dot / (norm_a * norm_b)
                
            similarities = [cosine_sim(query_emb, ce) for ce in chunk_embs]
            avg_score = sum(similarities) / len(similarities)
            
            status = "PASS" if avg_score >= threshold else "FAIL"
            
            return {
                "status": status,
                "avg_similarity": round(avg_score, 3),
                "threshold": threshold
            }
        except Exception as e:
            logger.error(f"Gemini embedding failed: {e}")
            return {"status": "ERROR", "avg_similarity": 0.0, "threshold": threshold, "details": str(e)}

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
            
        if self.use_gemini:
            return self._evaluate_with_gemini(query, retrieved_texts, threshold)
            
        query_emb = self.model.encode(query, convert_to_tensor=True)
        from sentence_transformers import util
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
