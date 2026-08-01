"""`score` — offline scoring of a response file against a ground-truth manifest.

Imports nothing from `transport/`, and `enforce_offline()` makes a socket attempt raise
even if something one day tries. The two together are what make "scoring never contacts
anything" a checkable property rather than a claim (§5.1, F18).
"""

from .offline import OfflineViolation, enforce_offline, is_enforced, offline
from .registry import BY_NAME, REGISTRY, CheckSpec, tier1_checks, tier2_checks
from .run import (
    FAIL,
    NOT_CAPTURED,
    NOT_ELIGIBLE,
    PASS,
    ScoringError,
    score,
    score_check,
)

__all__ = [
    "BY_NAME",
    "CheckSpec",
    "FAIL",
    "NOT_CAPTURED",
    "NOT_ELIGIBLE",
    "OfflineViolation",
    "PASS",
    "REGISTRY",
    "ScoringError",
    "enforce_offline",
    "is_enforced",
    "offline",
    "score",
    "score_check",
    "tier1_checks",
    "tier2_checks",
]
