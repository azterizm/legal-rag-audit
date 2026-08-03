"""The 17 evaluators.

Imported lazily, and that is load-bearing rather than a micro-optimisation. Three of
these modules import `sentence_transformers` at module scope, which pulls torch and
transformers — several hundred megabytes and several hundred transitive packages. A
plain re-export here would mean that touching `LeakageEvaluator`, which compares
substrings, imports a deep learning stack.

That breaks the §5.3 boundary in the direction that matters: `generate` installs
without the ML layer, so a package-level import of every evaluator makes the generate
path fail on a machine that is correctly provisioned. The lazy lookup below means each
check pays only for what it actually uses, and the Tier 1 checks pay nothing.

`tests/test_dependency_boundary.py` asserts this by importing the scoring registry in a
venv where torch is absent.
"""

from typing import TYPE_CHECKING, Any

_EXPORTS = {
    "HallucinationEvaluator": ".hallucination",
    "CitationEvaluator": ".citation",
    "RetrievalEvaluator": ".retrieval",
    "InjectionEvaluator": ".injection",
    "LeakageEvaluator": ".leakage",
    "AbstentionEvaluator": ".abstention",
    "ContradictionSurfacingEvaluator": ".conflict",
    "RoutingContaminationEvaluator": ".routing",
    "CrossClauseSynthesisEvaluator": ".synthesis",
    "MemoryManagementEvaluator": ".memory",
    "IndexFreshnessEvaluator": ".index_freshness",
    "LatencyPenaltyEvaluator": ".latency",
    "RetrievalDisambiguationEvaluator": ".disambiguation",
    "StructuralIntegrityEvaluator": ".structural",
    "EntityMaskingEvaluator": ".entity_masking",
    "ParametricBleedEvaluator": ".parametric_bleed",
    "CrossDocAttributionEvaluator": ".cross_doc_attribution",
}

#: Evaluators that load a model on construction. Named here so the boundary test can
#: assert the list is exactly the Tier 2 set in `score.registry`, rather than trusting
#: that nobody quietly added an import.
#:
#: Phase D took `ConfidenceEvaluator` off this list by deleting it. Abstention now scores
#: the presence of a specific claim rather than the entailment of a refusal, so it needs
#: no cross-encoder and no threshold, and it moved to Tier 1 (§8.2 #8).
MODEL_BACKED = frozenset({"HallucinationEvaluator", "RetrievalEvaluator"})

__all__ = [*_EXPORTS]

if TYPE_CHECKING:  # pragma: no cover - for type checkers, never imported at runtime
    from .abstention import AbstentionEvaluator
    from .citation import CitationEvaluator
    from .conflict import ContradictionSurfacingEvaluator
    from .cross_doc_attribution import CrossDocAttributionEvaluator
    from .disambiguation import RetrievalDisambiguationEvaluator
    from .entity_masking import EntityMaskingEvaluator
    from .hallucination import HallucinationEvaluator
    from .index_freshness import IndexFreshnessEvaluator
    from .injection import InjectionEvaluator
    from .latency import LatencyPenaltyEvaluator
    from .leakage import LeakageEvaluator
    from .memory import MemoryManagementEvaluator
    from .parametric_bleed import ParametricBleedEvaluator
    from .retrieval import RetrievalEvaluator
    from .routing import RoutingContaminationEvaluator
    from .structural import StructuralIntegrityEvaluator
    from .synthesis import CrossClauseSynthesisEvaluator


def __getattr__(name: str) -> Any:
    """Import the one module that defines `name`, on first use (PEP 562)."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    try:
        module = import_module(module_name, __name__)
    except ImportError as e:
        if name in MODEL_BACKED:
            raise ImportError(
                f"{name} needs the scoring dependencies, which are not installed.\n"
                f"  It is one of the Tier 2 checks: it runs a local model, so it lives\n"
                f"  behind the scoring layer rather than the base install (§5.3).\n"
                f"    pip install --require-hashes -r requirements/score.txt\n"
                f"  Original error: {e}"
            ) from e
        raise

    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
