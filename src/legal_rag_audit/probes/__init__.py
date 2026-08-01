"""Probe batteries and the eligibility they declare.

Pure data plus pydantic. No transport and no ML: `generate` reads a battery to know
what to ask, `score` reads the probe file it produced to know what may be counted, and
neither needs anything the other has.
"""

from .demo_battery import (
    BATTERY,
    BatteryEntry,
    build_ground_truth,
    build_probes,
    eligible_probe_ids,
    validate_battery,
)

__all__ = [
    "BATTERY",
    "BatteryEntry",
    "build_ground_truth",
    "build_probes",
    "eligible_probe_ids",
    "validate_battery",
]
