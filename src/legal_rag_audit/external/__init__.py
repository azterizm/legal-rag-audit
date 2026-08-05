"""Existing-corpus mode: the half of §9.1 that needs no upload endpoint (F25).

Ground truth here is **external and public** rather than ours by construction. A planted
invariant is true because we planted it; what section 108 said on 1 January 2011 is true
because the primary source says so, and every phrase in `anchors` carries the URL that
says it.

`ingest` is deliberately absent from these exports. It is the only module here that opens
a socket, and `score` reaches this package for the marker set — so importing it eagerly
would put an HTTP client on the offline path's import graph for no reason. The CLI
imports it directly, where the network is expected.
"""

from .anchors import ANCHORS, BY_ID, OGL, Anchor, AnchorError, Reading, validate_anchors
from .battery import (
    LICENSED,
    LICENSED_PROBES,
    POINT_IN_TIME,
    build_external_ground_truth,
    build_external_probes,
    external_probe_ids,
)
from .markers import (
    MARKER_CLASSES,
    NOT_SCORED,
    NOT_SCORED_REASON,
    Hit,
    MarkerClass,
    find,
)
from .store import Snapshot, Store, StoreError, excerpt_around, snapshot_for

__all__ = [
    "ANCHORS",
    "BY_ID",
    "LICENSED",
    "LICENSED_PROBES",
    "MARKER_CLASSES",
    "NOT_SCORED",
    "NOT_SCORED_REASON",
    "OGL",
    "POINT_IN_TIME",
    "Anchor",
    "AnchorError",
    "Hit",
    "MarkerClass",
    "Reading",
    "Snapshot",
    "Store",
    "StoreError",
    "build_external_ground_truth",
    "build_external_probes",
    "excerpt_around",
    "external_probe_ids",
    "find",
    "snapshot_for",
    "validate_anchors",
]
