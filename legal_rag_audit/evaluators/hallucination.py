import re
import logging
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)

class HallucinationEvaluator:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        # Minimum cosine similarity to consider a claim "supported" by a source
        self.similarity_threshold = 0.65 
        
    def _split_into_claims(self, text: str) -> List[str]:
        # Improved sentence boundary detection ignoring common abbreviations
        # Avoid splitting on things like "v.", "Inc.", "Mr.", "etc."
        # The lookbehind must include the period because the split is on the space following it.
        claims = re.split(r'(?<!\b[A-Z]\.)(?<!\bv\.)(?<!\bInc\.)(?<!\bet al\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)(?<=[.!?])\s+', text)
        return [c.strip() for c in claims if len(c.strip()) > 10]

    def evaluate(self, query: str, answer: str, source_texts: List[str], threshold: float) -> Dict[str, Any]:
        """
        Evaluates hallucination by extracting claims from the answer
        and ensuring every claim has a highly similar semantic match in the source_texts.
        """
        claims = self._split_into_claims(answer)
        if not claims:
            return {"status": "PASS", "score": 0.0, "threshold": threshold, "details": []}

        if not source_texts:
            # If there are no sources but there are claims, they are 100% hallucinated
            return {
                "status": "FAIL", 
                "score": 1.0, 
                "threshold": threshold,
                "details": [{
                    "query": query,
                    "claim": c,
                    "max_similarity_score": 0.0,
                    "source_match": None,
                    "verdict": "HALLUCINATED"
                } for c in claims]
            }

        # Encode sources once
        source_embeddings = self.model.encode(source_texts, convert_to_tensor=True)
        
        hallucinated_claims = []
        total_claims = len(claims)
        
        for claim in claims:
            claim_emb = self.model.encode(claim, convert_to_tensor=True)
            cosine_scores = util.cos_sim(claim_emb, source_embeddings)[0]
            max_score = cosine_scores.max().item()
            
            if max_score < self.similarity_threshold:
                hallucinated_claims.append({
                    "query": query,
                    "claim": claim,
                    "max_similarity_score": round(max_score, 3),
                    "source_match": None,
                    "verdict": "HALLUCINATED"
                })

        score = len(hallucinated_claims) / total_claims
        
        status = "FAIL" if score > threshold else "PASS"
        
        return {
            "status": status,
            "score": round(score, 3),
            "threshold": threshold,
            "details": hallucinated_claims
        }
