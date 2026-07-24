import os
from legal_rag_audit.evaluators.hallucination import HallucinationEvaluator

def test_hallucination():
    evaluator = HallucinationEvaluator(use_gemini=True, gemini_model="gemini-2.5-flash")
    answer = "In Smith v. Crown (2024) , the court:"
    source_texts = ["Smith v. Crown (2024) was a landmark case where the court awarded 150,000."]
    res = evaluator.evaluate(query="What was the ruling?", answer=answer, source_texts=source_texts, threshold=0.02)
    print("Test Answer:", answer)
    import json
    print("Result:", json.dumps(res, indent=2))

if __name__ == "__main__":
    test_hallucination()
