"""`validate` — the cheapest insurance in the engagement (§7.1).

Three neutral queries against the target, the raw body printed beside what the
configured JSONPaths pulled out of it, and every §7.1 setup condition named with a
remedy. No scoring, no report, nothing written to disk.

Two uses, and the second is why it is free:

1. **Before every run.** A wrong `answer_field` is our documented leading cause of
   false positives, and a false positive in a delivered report is not recoverable in
   this niche.
2. **Before any money changes hands.** It needs no corpus, no battery and no
   authorisation, so *run this and confirm the harness can read your API* costs the
   buyer nothing and discloses nothing.

**This package cannot reach the battery.** No module here imports `probes`, `plants`,
`corpus_loader` or `evaluators`, and `tests/test_validate.py` walks the import graph to
prove it rather than trusting the convention. The raw output goes to the target's
terminal, and a canary or an injection payload printed there is the product given away.
"""

from .diagnose import Diagnosis
from .neutral import NEUTRAL_PROBES, NeutralProbe
from .render import render
from .run import BATTERY_PROBE_COUNT, Observation, Validation, validate

__all__ = [
    "BATTERY_PROBE_COUNT",
    "Diagnosis",
    "NEUTRAL_PROBES",
    "NeutralProbe",
    "Observation",
    "Validation",
    "render",
    "validate",
]
