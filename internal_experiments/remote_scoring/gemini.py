"""Remote-scoring experiments. NOT part of the published package.

Lifted verbatim-in-behaviour out of legal_rag_audit/evaluators/{hallucination,
retrieval,confidence}.py when the remote-scoring path was removed from the shipped
tool (V2_FULL_PLAN.md §4.2, Phase A).

Read internal_experiments/README.md before running any of this. Two properties of the
code below are the reason it is not in the package:

  * ``score_claims`` issues ``num_runs`` generation calls per claim and averages them.
    That is non-deterministic by construction — the same responses produce a different
    report on a second run.
  * All three functions transmit corpus text and target answers to a third party. On
    that path the third party is a sub-processor and the run is a data-transfer event.

Nothing in ``legal_rag_audit`` imports this module, and nothing here imports
``legal_rag_audit``. ``requests`` is an undeclared dependency of this file alone; it is
deliberately absent from the project's dependency set.
"""

import json
import logging
import math
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "text-embedding-004:batchEmbedContents"
)


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")
    return key


def _strip_fences(text: str) -> str:
    if text.startswith("```json"):
        return text[7:-3]
    if text.startswith("```"):
        return text[3:-3]
    return text


def _split_into_claims(text: str) -> List[str]:
    text = re.sub(r"<[^>]+>", " ", text)
    claims = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        sentences = re.split(
            r"(?<!\b[A-Z]\.)(?<!\bv\.)(?<!\bInc\.)(?<!\bet al\.)"
            r"(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)(?<=[.!?])\s+",
            line,
        )
        for s in sentences:
            parts = re.split(r"(?:^|\s)[-•*]\s+", s)
            claims.extend([p.strip() for p in parts if len(p.strip()) > 10])
    return claims


def score_claims(
    answer: str,
    source_texts: List[str],
    model: str = "gemini-2.5-flash",
    num_runs: int = 3,
    support_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """Score each claim in ``answer`` for support by ``source_texts``.

    Returns one record per claim. ``num_runs`` calls are averaged per claim, which is
    where the non-determinism lives.
    """
    import requests

    url = _GENERATE_URL.format(model=model) + f"?key={_api_key()}"
    full_context = "\n\n".join(source_texts)

    evaluations = []
    for claim in _split_into_claims(answer):
        prompt = f"""You are a strict legal fact checker.

Context:
{full_context}

Claim: "{claim}"

Does the context completely support the claim?
Return ONLY a valid JSON object (no markdown, no markdown backticks) with exactly two keys:
- "score": A float between 0.0 and 1.0. (0.0 = completely unsupported/hallucinated, 1.0 = perfectly supported/entailed)
- "reasoning": A brief explanation of why this score was given."""

        scores, reasonings = [], []
        for _ in range(num_runs):
            try:
                resp = requests.post(
                    url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30
                )
                resp.raise_for_status()
                body = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                data = json.loads(_strip_fences(body))
                scores.append(float(data.get("score", 0.0)))
                reasonings.append(data.get("reasoning", "No reasoning provided."))
            except Exception as e:  # noqa: BLE001 — experiment code
                logger.error(f"Remote claim scoring failed: {e}")
                scores.append(0.0)

        avg = sum(scores) / len(scores) if scores else 0.0
        evaluations.append(
            {
                "claim": claim,
                "score": round(avg, 3),
                "reasoning": reasonings[0] if reasonings else "Evaluation failed.",
                "verdict": "UNSUPPORTED" if avg < support_threshold else "SUPPORTED",
                "runs": scores,
            }
        )
    return evaluations


def score_refusal(
    answer: str, model: str = "gemini-2.5-flash", num_runs: int = 3
) -> Dict[str, Any]:
    """Score whether ``answer`` is a refusal to answer.

    Note for the record: this is the judgment-shaped approach v2 replaces. §8.2 #8
    scores abstention by the *absence of the invariant class*, not by asking a model
    whether prose sounds like a refusal.
    """
    import requests

    url = _GENERATE_URL.format(model=model) + f"?key={_api_key()}"
    prompt = f"""You are a strict evaluator.

The system responded: "{answer}"

Does this response represent a refusal to answer (e.g., 'I don't know', 'I cannot answer', 'I don't have enough info')?
Return ONLY a valid JSON object (no markdown, no markdown backticks) with exactly two keys:
- "score": A float between 0.0 and 1.0. (0.0 = NOT a refusal, 1.0 = IS a clear refusal)
- "reasoning": A brief explanation of why this score was given."""

    scores, reasonings = [], []
    for _ in range(num_runs):
        try:
            resp = requests.post(
                url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30
            )
            resp.raise_for_status()
            body = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            data = json.loads(_strip_fences(body))
            scores.append(float(data.get("score", 0.0)))
            reasonings.append(data.get("reasoning", "No reasoning provided."))
        except Exception as e:  # noqa: BLE001 — experiment code
            logger.error(f"Remote refusal scoring failed: {e}")
            scores.append(0.0)

    avg = sum(scores) / len(scores) if scores else 0.0
    return {
        "score": round(avg, 3),
        "reasoning": reasonings[0] if reasonings else "Evaluation failed.",
        "runs": scores,
    }


def query_chunk_similarity(query: str, retrieved_texts: List[str]) -> List[float]:
    """Cosine similarity between ``query`` and each retrieved chunk, remotely embedded."""
    import requests

    url = _EMBED_URL + f"?key={_api_key()}"
    texts = [query] + retrieved_texts
    payload = {
        "requests": [
            {"model": "models/text-embedding-004", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
    }

    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    embeddings = [e["values"] for e in resp.json().get("embeddings", [])]
    if len(embeddings) != len(texts):
        raise ValueError("Mismatch in returned embeddings count.")

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return 0.0 if na == 0 or nb == 0 else dot / (na * nb)

    query_emb, chunk_embs = embeddings[0], embeddings[1:]
    return [cosine(query_emb, ce) for ce in chunk_embs]
