"""Manual check of the remote claim scorer. NOT a test; pytest must not collect it.

Requires GEMINI_API_KEY and a live network. Run from the repository root:

    python internal_experiments/remote_scoring/manual_hallucination_check.py

Run it twice and compare the ``runs`` arrays. The spread is the non-determinism that
kept this path out of the published package.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal_experiments.remote_scoring.gemini import score_claims


def main():
    answer = "In Smith v. Crown (2024) , the court:"
    source_texts = [
        "Smith v. Crown (2024) was a landmark case where the court awarded 150,000."
    ]
    print("Answer:", answer)
    print("Result:", json.dumps(score_claims(answer, source_texts), indent=2))


if __name__ == "__main__":
    main()
