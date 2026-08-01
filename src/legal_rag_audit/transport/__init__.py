"""HTTP, SSE and WebSocket access to the target. `generate` and `validate` only.

Nothing under `score/` may import this package, and a test asserts it (F18). The
offline claim in §5.1 is not a promise about how the scorer is written — it is a
property of what the scorer can reach.
"""

from .client import TargetClient

__all__ = ["TargetClient"]
