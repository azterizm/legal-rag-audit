import re
import logging
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder
import numpy as np
from tqdm import tqdm

logger = logging.getLogger(__name__)

class HallucinationEvaluator:
    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-base", use_gemini: bool = False, gemini_model: str = "gemini-2.5-flash"):
        self.use_gemini = use_gemini
        self.gemini_model = gemini_model
        self.similarity_threshold = 0.5 
        if not use_gemini:
            logger.info(f"Loading NLI cross-encoder model: {model_name}")
            self.model = CrossEncoder(model_name)
        else:
            logger.info(f"Using Gemini API ({self.gemini_model}) for Hallucination evaluation.")

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

    def _evaluate_with_gemini(self, query: str, answer: str, source_texts: List[str], threshold: float) -> Dict[str, Any]:
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

        import os
        import json
        import requests
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY environment variable not set.")
            return {"status": "ERROR", "score": 1.0, "threshold": threshold, "details": "Missing GEMINI_API_KEY"}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={api_key}"
        
        # We concatenate all source texts to provide the full context
        full_context = "\n\n".join(source_texts)
        # Gemini 2.5 flash has a massive context window so we don't need sliding windows
        
        hallucinated_claims = []
        all_evaluations = []
        total_claims = len(claims)
        
        num_runs = 3
        
        for claim in tqdm(claims, desc="Evaluating Claims with Gemini", unit="claim"):
            prompt = f"""You are a strict legal fact checker.

Context:
{full_context}

Claim: "{claim}"

Does the context completely support the claim? 
Return ONLY a valid JSON object (no markdown, no markdown backticks) with exactly two keys:
- "score": A float between 0.0 and 1.0. (0.0 = completely unsupported/hallucinated, 1.0 = perfectly supported/entailed)
- "reasoning": A brief explanation of why this score was given."""
            
            scores = []
            reasonings = []
            for _ in range(num_runs):
                try:
                    payload = {"contents": [{"parts": [{"text": prompt}]}]}
                    resp = requests.post(url, json=payload, timeout=30)
                    resp.raise_for_status()
                    response_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if response_text.startswith("```json"):
                        response_text = response_text[7:-3]
                    elif response_text.startswith("```"):
                        response_text = response_text[3:-3]
                    
                    data = json.loads(response_text)
                    scores.append(float(data.get("score", 0.0)))
                    reasonings.append(data.get("reasoning", "No reasoning provided."))
                except Exception as e:
                    logger.error(f"Gemini evaluation failed: {e}")
                    scores.append(0.0)
            
            avg_score = sum(scores) / len(scores) if scores else 0.0
            best_reasoning = reasonings[0] if reasonings else "Evaluation failed, no reasoning provided."
            
            evaluation_record = {
                "claim": claim,
                "score": round(avg_score, 3),
                "reasoning": best_reasoning,
                "verdict": "HALLUCINATED" if avg_score < self.similarity_threshold else "SUPPORTED"
            }
            all_evaluations.append(evaluation_record)
            
            if avg_score < self.similarity_threshold:
                hallucinated_claims.append(evaluation_record)

        score = len(hallucinated_claims) / total_claims if total_claims > 0 else 0.0
        status = "FAIL" if score > threshold else "PASS"
        
        return {
            "status": status,
            "score": round(score, 3),
            "threshold": threshold,
            "details": {
                "hallucinations": hallucinated_claims,
                "all_evaluations": all_evaluations
            }
        }

    def evaluate(self, query: str, answer: str, source_texts: List[str], threshold: float) -> Dict[str, Any]:
        if self.use_gemini:
            return self._evaluate_with_gemini(query, answer, source_texts, threshold)
            
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
