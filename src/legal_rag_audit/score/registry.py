"""The evaluator registry — what each check is, and what it needs to run.

One row per check. The row states the tier, the capabilities the response file must
carry, and the function that scores it. Three things fall out of holding it in one
place rather than in seventeen `if config.tests.x:` branches:

* **`tier` is what the implementation does, not what the plan wants it to do.** §8.1
  puts `abstention` in Tier 1 after Phase D rewrites it as an inverted presence check.
  Today it runs a cross-encoder, so it is registered Tier 2. Labelling it Tier 1 before
  the model comes out of the path would be the same class of claim Phase A removed —
  the register is only worth anything while it describes the code.
* **A check declares what it needs, so absence is detected rather than discovered.**
  Citation integrity needs the upload manifest; if the file carries none there is no
  set to test membership against, and the check reports NOT_CAPTURED rather than
  passing vacuously (F40).
* **The sensitivity gate can be written against the registry** rather than a hardcoded
  count (§14.2), so shipping an evaluator without a pathology profile fails the build
  instead of quietly shrinking the denominator.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..config import ThresholdsConfig
from ..interchange import Expectation, Probe, Response

#: What a check needs the response file to carry, beyond an answer.
#:
#: `answer` is implied by every check and listed anyway, because a record with `error`
#: set has no answer and the same code path handles both.
ANSWER = "answer"
CITATIONS = "citations"
RETRIEVED_CHUNKS = "retrieved_chunks"
DOCUMENT_IDS = "document_ids"
TIMING = "timing"

CAPABILITY_HELP = {
    ANSWER: "an answer (the record carries a transport error instead)",
    CITATIONS: "citations (`citations` is null — not captured)",
    RETRIEVED_CHUNKS: "retrieved chunks (`retrieved_chunks` is null — not captured)",
    DOCUMENT_IDS: (
        "the upload manifest (`document_ids` in the capture-notes header). Citation "
        "integrity is set membership; with no set there is nothing to test against"
    ),
    TIMING: "response timings (`total_ms` is null — not captured)",
}


@dataclass
class CheckInput:
    """Everything one check is allowed to see."""

    check: str
    #: Probes the probe file declared eligible for this check. The denominator (F39).
    probes: list[Probe]
    #: probe_id -> its records, ordered by pass_index.
    responses: dict[str, list[Response]]
    expectations: dict[str, Expectation]
    document_ids: Optional[list[str]]
    thresholds: ThresholdsConfig

    def pairs(self) -> list[tuple[Probe, Response, Optional[Expectation]]]:
        """Usable (probe, response, expectation) triples, in probe then pass order."""
        out = []
        for probe in self.probes:
            for response in self.responses.get(probe.probe_id, []):
                if response.usable:
                    out.append(
                        (probe, response, self.expectations.get(probe.probe_id))
                    )
        return out


@dataclass
class CheckOutcome:
    """What one check concluded."""

    status: str
    scored: int
    failed: int
    detail: dict[str, Any] = field(default_factory=dict)
    #: Named when part of the check could not run. Printed in the report next to the
    #: result, so a partial check never reads as a complete one.
    partial: Optional[str] = None


Scorer = Callable[[CheckInput], CheckOutcome]


@dataclass(frozen=True)
class CheckSpec:
    name: str
    tier: int
    needs: frozenset[str]
    scorer: Scorer
    #: One line, printed in the report beside the result.
    recipe: str


# --------------------------------------------------------------------------------
# Scoring helpers
# --------------------------------------------------------------------------------


def per_probe(
    fn: Callable[[Probe, Response, Optional[Expectation], CheckInput], dict[str, Any]],
) -> Scorer:
    """Build a scorer that applies `fn` to each usable record and counts the results.

    Counts, not a rate (§3.5). The denominator is the number of records actually
    scored, which is stated alongside; dividing here would produce a percentage whose
    denominator the reader cannot see.
    """

    def scorer(data: CheckInput) -> CheckOutcome:
        results = []
        failed = 0
        for probe, response, expectation in data.pairs():
            result = fn(probe, response, expectation, data)
            result["probe_id"] = probe.probe_id
            result["pass_index"] = response.pass_index
            if result.get("status") == "FAIL":
                failed += 1
            results.append(result)

        return CheckOutcome(
            status="FAIL" if failed else "PASS",
            scored=len(results),
            failed=failed,
            detail={"per_probe": results},
        )

    return scorer


#: Tier 2 evaluators load a model on construction. Built once per process and reused,
#: so a multi-pass run does not pay for it per record.
_TIER2_CACHE: dict[str, Any] = {}


def _tier2(name: str, build: Callable[[], Any]) -> Any:
    if name not in _TIER2_CACHE:
        _TIER2_CACHE[name] = build()
    return _TIER2_CACHE[name]


def _tuples(rows: Any) -> list[tuple]:
    """JSON has no tuples; the evaluators want them."""
    return [tuple(row) for row in (rows or [])]


class GroundTruthIncomplete(Exception):
    """A check has no expectation to score against. A setup problem, not a finding."""


def _require(
    expectation: Optional[Expectation], field_name: str, check: str, probe_id: str
) -> list[str]:
    """Return a non-empty expectation list, or abort.

    A check whose ground truth is missing cannot produce a result in either direction.
    Returning PASS would assert something we never tested; returning FAIL would be a
    finding manufactured from our own missing data (NF9). So it stops the run.
    """
    values = getattr(expectation, field_name, None) if expectation else None
    if not values:
        raise GroundTruthIncomplete(
            f"{check}: probe {probe_id!r} has no `{field_name}` in the ground-truth "
            f"manifest.\n"
            f"  This check scores against it, so there is nothing to compare. Neither\n"
            f"  a pass nor a failure would mean anything here."
        )
    return values


# --------------------------------------------------------------------------------
# Tier 1 — no model in the scoring path
# --------------------------------------------------------------------------------


def _score_cross_tenant_leakage(probe, response, expectation, data):
    from ..evaluators import LeakageEvaluator

    return LeakageEvaluator().evaluate(
        answer=response.answer,
        tenant_b_canaries=expectation.must_not_contain if expectation else [],
    )


def _score_injection(probe, response, expectation, data):
    from ..evaluators import InjectionEvaluator

    return InjectionEvaluator().evaluate(answer=response.answer)


def _score_citation_integrity(probe, response, expectation, data):
    from ..evaluators import CitationEvaluator

    return CitationEvaluator().evaluate(
        returned_citations=response.citations or [],
        valid_document_ids=set(data.document_ids or []),
    )


def _score_index_freshness(probe, response, expectation, data):
    from ..evaluators import CacheInvalidationEvaluator

    check, pid = "index_freshness", probe.probe_id
    return CacheInvalidationEvaluator().evaluate(
        answer=response.answer,
        stale_fact=_require(expectation, "must_not_contain", check, pid)[0],
        fresh_fact=_require(expectation, "must_contain", check, pid)[0],
    )


def _score_entity_masking(probe, response, expectation, data):
    from ..evaluators import EntityMaskingEvaluator

    params = expectation.legacy_params
    raw = response.raw_response if isinstance(response.raw_response, dict) else None
    return EntityMaskingEvaluator().evaluate(
        answer=response.answer,
        expected_pii_pairs=_tuples(params.get("expected_pii_pairs")),
        forbidden_swaps=_tuples(params.get("forbidden_swaps")),
        raw_response=raw,
    )


def _score_parametric_bleed(probe, response, expectation, data):
    from ..evaluators import ParametricBleedEvaluator

    return ParametricBleedEvaluator().evaluate(
        answer=response.answer,
        parametric_canaries=expectation.legacy_params.get("parametric_canaries", []),
        citations=response.citations or [],
    )


def _score_routing(probe, response, expectation, data):
    from ..evaluators import RoutingContaminationEvaluator

    return RoutingContaminationEvaluator().evaluate(
        answer=response.answer,
        out_of_bounds_keywords=expectation.must_not_contain if expectation else [],
    )


def _score_contradiction(probe, response, expectation, data):
    from ..evaluators import ContradictionSurfacingEvaluator

    return ContradictionSurfacingEvaluator().evaluate(
        answer=response.answer,
        expected_conflicts=expectation.must_contain if expectation else [],
    )


def _score_attribution(probe, response, expectation, data):
    from ..evaluators import CrossDocAttributionEvaluator

    return CrossDocAttributionEvaluator().evaluate(
        answer=response.answer,
        expected_facts_with_sources=_tuples(
            expectation.legacy_params.get("expected_facts_with_sources")
        ),
        citations=response.citations or [],
    )


def _score_clause_synthesis(probe, response, expectation, data):
    from ..evaluators import CrossClauseSynthesisEvaluator

    return CrossClauseSynthesisEvaluator().evaluate(
        answer=response.answer,
        required_facts=expectation.must_contain if expectation else [],
    )


def _score_structural(probe, response, expectation, data):
    from ..evaluators import StructuralIntegrityEvaluator

    return StructuralIntegrityEvaluator().evaluate(
        answer=response.answer,
        required_relational_facts=_require(
            expectation, "must_contain", "structural_integrity", probe.probe_id
        ),
        forbidden_conflations=expectation.must_not_contain,
    )


def _score_disambiguation(probe, response, expectation, data):
    from ..evaluators import RetrievalDisambiguationEvaluator

    return RetrievalDisambiguationEvaluator().evaluate(
        answer=response.answer,
        expected_canaries=_require(
            expectation, "must_contain", "disambiguation", probe.probe_id
        ),
        forbidden_canaries=expectation.must_not_contain,
        latency_seconds=(response.total_ms or 0) / 1000.0,
    )


def _score_context_memory(probe, response, expectation, data):
    from ..evaluators import MemoryManagementEvaluator

    return MemoryManagementEvaluator().evaluate(
        answer=response.answer,
        target_reference=_require(
            expectation, "must_contain", "context_memory", probe.probe_id
        )[0],
    )


def _score_latency(data: CheckInput) -> CheckOutcome:
    """Compare a baseline probe against the one designed to provoke a rewrite.

    Which probe plays which role is in the ground truth, not the probe file — a battery
    that announced *this is the timed trap* would let a target treat it differently.
    """
    from ..evaluators import LatencyPenaltyEvaluator

    pairing = next(
        (e.legacy_params for e in data.expectations.values() if e.legacy_params), {}
    )
    baseline_id = pairing.get("baseline_probe")
    contra_id = pairing.get("contradictory_probe")

    def first(probe_id):
        records = [r for r in data.responses.get(probe_id, []) if r.usable]
        return records[0] if records else None

    baseline = first(baseline_id) if baseline_id else None
    contradictory = first(contra_id) if contra_id else None

    if baseline is None or contradictory is None:
        return CheckOutcome(
            status="PASS",
            scored=0,
            failed=0,
            detail={},
            partial=(
                "the baseline and contradictory probes were not both answered, so "
                "there is no pair to compare"
            ),
        )

    # TTFB is null on every record the current transport produces (see generate/run.py).
    # Zero disables the evaluator's ratio and ceiling checks on TTFB rather than
    # inventing a value, and `partial` says so — a check that quietly compared total
    # against itself under two names would look like it had run.
    ttfb_captured = baseline.ttfb_ms is not None and contradictory.ttfb_ms is not None

    result = LatencyPenaltyEvaluator().evaluate(
        baseline_ttfb=(baseline.ttfb_ms or 0) / 1000.0,
        baseline_total=(baseline.total_ms or 0) / 1000.0,
        contradictory_ttfb=(contradictory.ttfb_ms or 0) / 1000.0,
        contradictory_total=(contradictory.total_ms or 0) / 1000.0,
    )
    result["baseline_probe"] = baseline_id
    result["contradictory_probe"] = contra_id

    return CheckOutcome(
        status=result.get("status", "PASS"),
        scored=1,
        failed=1 if result.get("status") == "FAIL" else 0,
        detail=result,
        partial=(
            None
            if ttfb_captured
            else (
                "time to first byte was not captured, so only total response time was "
                "compared. The TTFB-to-total gap this check reads as catch-and-"
                "regenerate was not measured"
            )
        ),
    )


# --------------------------------------------------------------------------------
# Tier 2 — a model is in the scoring path, and the report says which one
# --------------------------------------------------------------------------------


def _score_unsupported_assertions(probe, response, expectation, data):
    from ..evaluators import HallucinationEvaluator

    evaluator = _tier2("unsupported_assertions", HallucinationEvaluator)
    chunks = [c.text for c in (response.retrieved_chunks or [])]
    return evaluator.evaluate(
        query=response.query,
        answer=response.answer,
        # Scored against what the system actually retrieved, not against the whole
        # corpus. A claim the retrieved material does not support is the finding; a
        # claim supported by a document the system never fetched is not grounding.
        source_texts=chunks,
        threshold=data.thresholds.max_hallucination_rate,
    )


def _score_retrieval_relevance(probe, response, expectation, data):
    from ..evaluators import RetrievalEvaluator

    evaluator = _tier2("retrieval_relevance", RetrievalEvaluator)
    return evaluator.evaluate(
        query=response.query,
        retrieved_texts=[c.text for c in (response.retrieved_chunks or [])],
        threshold=data.thresholds.min_retrieval_relevance,
    )


def _score_abstention(probe, response, expectation, data):
    from ..evaluators import ConfidenceEvaluator

    evaluator = _tier2("abstention", ConfidenceEvaluator)
    return evaluator.evaluate(answer=response.answer)


# --------------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------------

REGISTRY: tuple[CheckSpec, ...] = (
    CheckSpec(
        name="cross_tenant_leakage",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_cross_tenant_leakage),
        recipe="Multi-type canary; substring presence",
    ),
    CheckSpec(
        name="injection_resistance",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_injection),
        recipe="Payload demanding a verifiable side effect; prefix match",
    ),
    CheckSpec(
        name="citation_integrity",
        tier=1,
        needs=frozenset({ANSWER, CITATIONS, DOCUMENT_IDS}),
        scorer=per_probe(_score_citation_integrity),
        recipe="Set membership of cited IDs against the upload manifest",
    ),
    CheckSpec(
        name="index_freshness",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_index_freshness),
        recipe="Update a planted fact; check old token against new",
    ),
    CheckSpec(
        name="entity_masking",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_entity_masking),
        recipe="Exact match on entity; counterparty-swap check across pairs",
    ),
    CheckSpec(
        name="parametric_bleed",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_parametric_bleed),
        recipe="Inverted — presence of a known out-of-corpus fact",
    ),
    CheckSpec(
        name="routing_contamination",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_routing),
        recipe="Inverted — presence of an out-of-bounds fact",
    ),
    CheckSpec(
        name="abstention",
        # §8.1 puts this in Tier 1 once Phase D rewrites it as presence of the answer it
        # should not have given. The shipped implementation runs a cross-encoder over
        # refusal phrasings, so it is Tier 2 until that lands.
        tier=2,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_abstention),
        recipe="Cross-encoder over refusal phrasings (Tier 1 recipe pending Phase D)",
    ),
    CheckSpec(
        name="contradiction_surfacing",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_contradiction),
        recipe="Both planted values present ⇒ surfaced; one ⇒ silently picked",
    ),
    CheckSpec(
        name="attribution",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_attribution),
        recipe="Adjacency — planted fact and correct document ID in one sentence",
    ),
    CheckSpec(
        name="clause_synthesis",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_clause_synthesis),
        recipe="Required-facts checklist, including the planted exclusion",
    ),
    CheckSpec(
        name="structural_integrity",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_structural),
        recipe="Invariant planted deep in a nested list; relational query",
    ),
    CheckSpec(
        name="disambiguation",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_disambiguation),
        recipe="Distinct invariant under each colliding article number",
    ),
    CheckSpec(
        name="context_memory",
        tier=1,
        needs=frozenset({ANSWER}),
        scorer=per_probe(_score_context_memory),
        recipe="Distinct invariant per referent; which one the pronoun resolved to",
    ),
    CheckSpec(
        name="latency",
        tier=1,
        needs=frozenset({ANSWER, TIMING}),
        scorer=_score_latency,
        recipe="TTFB and total as measurements; the interpretation is labelled inference",
    ),
    CheckSpec(
        name="unsupported_assertions",
        tier=2,
        needs=frozenset({ANSWER, RETRIEVED_CHUNKS}),
        scorer=per_probe(_score_unsupported_assertions),
        recipe="Sentence-level NLI entailment against retrieved chunks",
    ),
    CheckSpec(
        name="retrieval_relevance",
        tier=2,
        needs=frozenset({ANSWER, RETRIEVED_CHUNKS}),
        scorer=per_probe(_score_retrieval_relevance),
        recipe="Cosine similarity over retrieved chunks",
    ),
)

BY_NAME: dict[str, CheckSpec] = {spec.name: spec for spec in REGISTRY}


def tier1_checks() -> list[str]:
    return [s.name for s in REGISTRY if s.tier == 1]


def tier2_checks() -> list[str]:
    return [s.name for s in REGISTRY if s.tier == 2]
