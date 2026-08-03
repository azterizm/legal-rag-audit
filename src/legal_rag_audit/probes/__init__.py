"""Probe batteries and the eligibility they declare.

Pure data plus pydantic, over the planting pipeline. No transport and no ML: `generate`
reads a battery to know what to ask, `score` reads the probe file it produced to know
what may be counted, and neither needs anything the other has.
"""

from .battery import (
    BATTERY,
    UNTESTABLE_ON_THE_BATTERY,
    BatteryEntry,
    BatteryError,
    P,
    build_ground_truth,
    build_probes,
    eligible_probe_ids,
    planted_corpus,
    validate_battery,
)

__all__ = [
    "BATTERY",
    "BatteryEntry",
    "BatteryError",
    "P",
    "UNTESTABLE_ON_THE_BATTERY",
    "build_ground_truth",
    "build_probes",
    "eligible_probe_ids",
    "planted_corpus",
    "validate_battery",
]
