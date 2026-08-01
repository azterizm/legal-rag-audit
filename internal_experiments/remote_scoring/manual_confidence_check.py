"""Manual check of the remote refusal scorer. NOT a test; pytest must not collect it.

Requires GEMINI_API_KEY and a live network. Run from the repository root:

    python internal_experiments/remote_scoring/manual_confidence_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal_experiments.remote_scoring.gemini import score_refusal


def main():
    answer = "The capital of France is Paris."
    print("Answer:", answer)
    print("Result:", score_refusal(answer))


if __name__ == "__main__":
    main()
