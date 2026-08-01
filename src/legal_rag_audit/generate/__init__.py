"""`generate` — ask the battery, record what came back, score nothing.

Optional by design (§5.1). A target may replace this entire package with their own
harness and hand back a conforming `responses.jsonl`; `score` cannot tell, and the
evidence being theirs is what makes a finding hard to dismiss as our prompting.
"""

from .run import GenerationError, Generator, generate

__all__ = ["GenerationError", "Generator", "generate"]
