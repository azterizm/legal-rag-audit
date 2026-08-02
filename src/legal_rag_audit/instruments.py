"""The Tier 2 instruments, named in one place.

A Tier 2 number means nothing without the instrument that produced it: §4.1 requires
the model name, its version and its threshold in the manifest, because "12 unsupported
assertions" is a statement about a model and a line, not about a product.

The names live here as constants rather than being read off the evaluators, for one
practical reason: the manifest has to state them on runs where the Tier 2 layer is
deliberately *not* installed (`--skip-tier2`). Reading them from the classes would
mean importing sentence-transformers to write a manifest for a run that imported no
models at all. `tests/test_manifest.py` asserts these constants still match the
evaluator defaults, so the two cannot drift apart silently.
"""

from dataclasses import dataclass
from typing import Any, Final, Optional

#: Cross-encoder used for entailment. Every claim about grounding on Tier 2 comes
#: from this model.
ENTAILMENT_MODEL: Final = "cross-encoder/nli-deberta-v3-base"

#: Sentence embedding model used for retrieval similarity.
EMBEDDING_MODEL: Final = "all-MiniLM-L6-v2"


@dataclass(frozen=True)
class Instrument:
    """One model in the scoring path, and the line it is read against."""

    check: str
    role: str
    model: str
    #: Attribute on ThresholdsConfig holding the line, or None when the number is
    #: hard-coded in the evaluator and the operator cannot set it.
    setting: Optional[str]
    #: Used when `setting` is None. Kept here so the manifest can state the number
    #: without instantiating anything.
    default: float
    #: What the number means. A similarity line and a tolerated rate are different
    #: kinds of threshold and a report that prints both as "threshold: 0.85" invites
    #: the wrong reading.
    kind: str
    #: Key in the evaluator's per-record result holding the number the line is read
    #: against. F24 reports these as a distribution, because a Tier 2 check that
    #: printed only PASS/FAIL would hide how close to the line every record sat —
    #: and the line is a setting of ours, not a standard.
    score_key: str
    #: `higher` or `lower`. Which side of the line passes. Both exist here, and a
    #: distribution drawn without it marks the line on the wrong side.
    better: str
    #: What the number is, for the axis label on the page.
    unit: str


INSTRUMENTS: Final[tuple[Instrument, ...]] = (
    Instrument(
        check="unsupported_assertions",
        role="entailment",
        model=ENTAILMENT_MODEL,
        setting="max_hallucination_rate",
        default=0.02,
        kind="rate tolerated across the eligible probes",
        score_key="score",
        better="lower",
        unit="fraction of the answer's claims the retrieved chunks did not entail",
    ),
    Instrument(
        check="retrieval_relevance",
        role="embedding similarity",
        model=EMBEDDING_MODEL,
        setting="min_retrieval_relevance",
        default=0.85,
        kind="cosine similarity line a chunk must clear",
        score_key="avg_similarity",
        better="higher",
        unit="mean cosine similarity between the query and the retrieved chunks",
    ),
    Instrument(
        check="abstention",
        role="entailment against canonical refusals",
        model=ENTAILMENT_MODEL,
        # Not configurable in this build: score/registry.py calls
        # ConfidenceEvaluator.evaluate() without a threshold, so the evaluator's own
        # default applies. Recorded rather than quietly inherited — an undisclosed
        # number in the scoring path is exactly what §4.1 exists to prevent.
        setting=None,
        default=0.5,
        kind="entailment line against canonical refusal phrasings",
        score_key="max_similarity",
        better="higher",
        unit="strongest entailment against any canonical refusal",
    ),
)

BY_CHECK: Final[dict[str, Instrument]] = {i.check: i for i in INSTRUMENTS}


def installed_version() -> tuple[Optional[str], Optional[str]]:
    """The installed sentence-transformers version, or why it is not known.

    Never imports the package: `importlib.metadata` reads the installed distribution
    metadata, so this stays cheap and stays torch-free.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("sentence-transformers"), None
    except PackageNotFoundError:
        return None, (
            "sentence-transformers is not installed in this environment "
            "(the `score` extra provides it)"
        )


def describe(thresholds: Any) -> list[dict[str, Any]]:
    """The manifest rows for every model in the scoring path.

    `thresholds` is a ThresholdsConfig; typed loosely so this module imports nothing.
    """
    library, why_not = installed_version()
    rows = []
    for instrument in INSTRUMENTS:
        if instrument.setting is None:
            value = instrument.default
            source = "evaluator default — not configurable in this build"
        else:
            value = getattr(thresholds, instrument.setting, instrument.default)
            source = f"thresholds.{instrument.setting}"
        rows.append(
            {
                "check": instrument.check,
                "role": instrument.role,
                "model": instrument.model,
                # Weights are resolved by name at load time. This build pins the
                # library, not the checkpoint, so a re-run months later could load
                # different weights under the same name. Stated, not hidden.
                "weights_revision": None,
                "weights_revision_unavailable": (
                    "this build resolves model weights by name and does not pin a "
                    "checkpoint revision"
                ),
                "library": "sentence-transformers",
                "library_version": library,
                "library_version_unavailable": why_not,
                "threshold": value,
                "threshold_source": source,
                "threshold_kind": instrument.kind,
            }
        )
    return rows


def threshold_for(check: str, thresholds: Any) -> float:
    """The line this check is read against, wherever it comes from."""
    instrument = BY_CHECK[check]
    if instrument.setting is None:
        return instrument.default
    return getattr(thresholds, instrument.setting, instrument.default)
