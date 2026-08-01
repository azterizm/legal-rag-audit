import logging
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

class ConfidenceEvaluator:
    """Abstention check, scored locally against a fixed set of canonical refusals.

    The model runs in-process. No request leaves this machine during scoring.

    Known limitation, carried until Phase D: this enumerates refusal phrasings, and
    "I don't have that" has a thousand of them. V2_FULL_PLAN.md §8.2 #8 replaces it
    with an inverted check — the failure is the *presence* of a specific claim the
    corpus cannot support, not the absence of refusal language.
    """

    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-base"):
        self.model_name = model_name

        self.canonical_refusals = [
            "I do not have enough information to answer that question.",
            "The provided documents do not contain the answer.",
            "I cannot answer this based on the available context.",
            "There is insufficient information to provide a reliable answer.",
            "I don't have that information in the materials available to me."
        ]

        logger.info(f"Loading NLI model for confidence evaluation: {model_name}")
        self.model = CrossEncoder(model_name)

    def evaluate(self, answer: str, threshold: float = 0.5) -> Dict[str, Any]:
        if not answer:
            return {
                "status": "FAIL",
                "refused_correctly": False,
                "max_similarity": 0.0,
                "threshold": threshold,
                "details": "Model attempted to answer without context or provided empty answer."
            }

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
