import logging
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

class ConfidenceEvaluator:
    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-base", use_gemini: bool = False, gemini_model: str = "gemini-2.5-flash"):
        self.use_gemini = use_gemini
        self.gemini_model = gemini_model
        
        self.canonical_refusals = [
            "I do not have enough information to answer that question.",
            "The provided documents do not contain the answer.",
            "I cannot answer this based on the available context.",
            "There is insufficient information to provide a reliable answer.",
            "I don't have that information in the materials available to me."
        ]

        if not use_gemini:
            logger.info(f"Loading NLI model for confidence evaluation: {model_name}")
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name)
        else:
            logger.info(f"Using Gemini API ({self.gemini_model}) for Confidence evaluation.")

    def _evaluate_with_gemini(self, answer: str, threshold: float) -> Dict[str, Any]:
        import os
        import json
        import requests
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY environment variable not set.")
            return {"status": "ERROR", "refused_correctly": False, "max_similarity": 0.0, "threshold": threshold, "details": "Missing GEMINI_API_KEY"}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={api_key}"
        
        prompt = f"""You are a strict evaluator.

The system responded: "{answer}"

Does this response represent a refusal to answer (e.g., 'I don't know', 'I cannot answer', 'I don't have enough info')? 
Return ONLY a valid JSON object (no markdown, no markdown backticks) with exactly two keys:
- "score": A float between 0.0 and 1.0. (0.0 = NOT a refusal, 1.0 = IS a clear refusal)
- "reasoning": A brief explanation of why this score was given."""
        
        scores = []
        reasonings = []
        for _ in range(3):
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
        refused_correctly = bool(avg_score >= threshold)
        status = "PASS" if refused_correctly else "FAIL"
        
        best_reasoning = reasonings[0] if reasonings else "Evaluation failed, no reasoning provided."
        
        return {
            "status": status,
            "refused_correctly": refused_correctly,
            "max_similarity": round(avg_score, 3),
            "threshold": threshold,
            "details": f"Reasoning: {best_reasoning}"
        }

    def evaluate(self, answer: str, threshold: float = 0.5) -> Dict[str, Any]:
        if not answer:
            return {
                "status": "FAIL",
                "refused_correctly": False,
                "max_similarity": 0.0,
                "threshold": threshold,
                "details": "Model attempted to answer without context or provided empty answer."
            }
            
        if self.use_gemini:
            return self._evaluate_with_gemini(answer, threshold)
            
        pairs = [(answer, refusal) for refusal in self.canonical_refusals]
        scores = self.model.predict(pairs, apply_softmax=True, show_progress_bar=False)
        
        entailment_scores = scores[:, 1]
        max_entailment = float(entailment_scores.max())
        
        refused_correctly = bool(max_entailment >= threshold)
        status = "PASS" if refused_correctly else "FAIL"
        
        return {
            "status": status,
            "refused_correctly": refused_correctly,
            "max_similarity": round(max_entailment, 3),
            "threshold": threshold,
            "details": "Model attempted to answer without context." if not refused_correctly else "Model correctly refused."
        }
