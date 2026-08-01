import os
from legal_rag_audit.evaluators.confidence import ConfidenceEvaluator

def test_confidence():
    # Make sure we have an API key, we will just assume it's in env
    evaluator = ConfidenceEvaluator(use_gemini=True, gemini_model="gemini-2.5-flash")
    answer = "The capital of France is Paris."
    res = evaluator.evaluate(answer, threshold=0.5)
    print("Test Answer:", answer)
    print("Result:", res)

if __name__ == "__main__":
    test_confidence()
