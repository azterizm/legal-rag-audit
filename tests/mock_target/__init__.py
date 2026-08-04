"""The pathological reference target (V2_FULL_PLAN.md §14.1).

The answer to *"how do I know your tool is right?"* — a local server that can be told to
exhibit each failure mode the battery claims to find, so the harness can be run against
a system whose defects are known in advance. Two numbers come out of it, and §14.2 makes
both of them publishable claims about our own instrument:

* **sensitivity** — every shipped evaluator, given a target exhibiting the defect it
  looks for, reports it;
* **specificity** — a target that behaves correctly produces no findings at all.

The second is the one that costs money to get wrong, which is why §14.2 makes a false
positive a release blocker and a missed detection merely a bug.

Lives under `tests/` rather than in the package. It is not a product surface: shipping it
would put a fake legal-RAG system in the wheel, and the first person to point it at
something would be running our mock against their data.
"""

from .oracle import Chunk, Oracle, OracleError, Reply, answered_probe_ids
from .pathologies import BY_NAME, CLEAN, PROFILES, Profile
from .server import Running, Target, serve

__all__ = [
    "BY_NAME",
    "CLEAN",
    "Chunk",
    "Oracle",
    "OracleError",
    "PROFILES",
    "Profile",
    "Reply",
    "Running",
    "Target",
    "answered_probe_ids",
    "serve",
]
