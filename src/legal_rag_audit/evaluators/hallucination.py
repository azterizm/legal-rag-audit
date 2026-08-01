import re
import logging
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder
from tqdm import tqdm

logger = logging.getLogger(__name__)

class HallucinationEvaluator:
    """Sentence-level entailment against retrieved source text, scored locally.

    The model runs in-process. No request leaves this machine during scoring.
    """

    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-base"):
        self.model_name = model_name
        self.similarity_threshold = 0.5
        logger.info(f"Loading NLI cross-encoder model: {model_name}")
        self.model = CrossEncoder(model_name)

    def _strip_html(self, text: str) -> str:
        return re.sub(r'<[^>]+>', '', text)

    def _split_into_claims(self, text: str) -> List[str]:
        # Replace HTML tags with spaces so words don't merge (e.g. "word<br>word" -> "word word")
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Split on newlines and sentence boundaries
        claims = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Split into sentences using punctuation, avoiding common abbreviations
            sentences = re.split(r'(?<!\b[A-Z]\.)(?<!\bv\.)(?<!\bInc\.)(?<!\bet al\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)(?<=[.!?])\s+', line)
            
            for s in sentences:
                # Also split on bullet points if any remain
                parts = re.split(r'(?:^|\s)[-•*]\s+', s)
                claims.extend([p.strip() for p in parts if len(p.strip()) > 10])
                
        return claims

    def _split_into_paragraphs(self, text: str) -> List[str]:
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 20]
        
        # Combine every 3 adjacent paragraphs to preserve context across splits
        chunks = []
        for i in range(len(paragraphs)):
            chunk = "\n\n".join(paragraphs[max(0, i-1):i+2])
            chunks.append(chunk)
        return chunks

    def evaluate(self, query: str, answer: str, source_texts: List[str], threshold: float) -> Dict[str, Any]:
        claims = self._split_into_claims(answer)
        if not claims:
            return {"status": "PASS", "score": 0.0, "threshold": threshold, "details": []}

        if not source_texts:
            return {
                "status": "FAIL", 
                "score": 1.0, 
                "threshold": threshold,
                "details": [{
                    "query": query,
                    "claim": c,
                    "max_entailment_score": 0.0,
                    "source_match": None,
                    "verdict": "HALLUCINATED"
                } for c in claims]
            }

        source_chunks = []
        for st in source_texts:
            source_chunks.extend(self._split_into_paragraphs(st))
            
        if not source_chunks:
            source_chunks = source_texts

        hallucinated_claims = []
        total_claims = len(claims)
        
        for claim in tqdm(claims, desc="Evaluating Claims", unit="claim"):
            pairs = [(chunk, claim) for chunk in source_chunks]
            scores = self.model.predict(pairs, apply_softmax=True, show_progress_bar=False)
            
            entailment_scores = scores[:, 1]
            max_entailment_score = float(entailment_scores.max())
            best_chunk_idx = int(entailment_scores.argmax())
            
            if max_entailment_score < self.similarity_threshold:
                hallucinated_claims.append({
                    "query": query,
                    "claim": claim,
                    "max_entailment_score": round(max_entailment_score, 3),
                    "source_match": source_chunks[best_chunk_idx] if len(source_chunks) > best_chunk_idx else None,
                    "verdict": "HALLUCINATED"
                })

        score = len(hallucinated_claims) / total_claims if total_claims > 0 else 0.0
        status = "FAIL" if score > threshold else "PASS"
        
        return {
            "status": status,
            "score": round(score, 3),
            "threshold": threshold,
            "details": hallucinated_claims
        }
