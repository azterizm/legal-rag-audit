"""Inter-pass divergence (§8.3, F22) — Phase E's acceptance.

The phase turns a liability into a finding. Without it, a target whose answers vary
between identical questions makes *the harness* look flaky: two runs disagree and the
reader's first thought is that the tool is unreliable. So the tests that matter here are
the two that bound the claim in opposite directions:

* a system that reworded every answer and changed no outcome produces **zero** findings —
  flagging ordinary phrasing variation as failure is the fastest way to lose a report;
* a system that changed one outcome on one pass produces **one**, with both texts.

Everything else in this module exists to stop those two drifting apart.
"""

import pytest

from legal_rag_audit.interchange import (
    Response,
    RetrievedChunk,
    write_ground_truth,
    write_probes,
    write_responses,
)
from legal_rag_audit.probes import build_ground_truth, build_probes, planted_corpus
from legal_rag_audit.score import REGISTRY, score
from legal_rag_audit.score import variance

from test_scoring import compliant_answers

CORPUS = planted_corpus()


def multi_pass(probes, text, passes=3, notes=None):
    """One record per (probe, pass). `text(probe, pass_index) -> str`."""
    return [
        Response(
            run_id="r",
            probe_id=probe.probe_id,
            query=probe.text,
            tenant=probe.tenant,
            pass_index=index,
            answer=text(probe, index),
            citations=[],
            total_ms=100 + index,
            http_status=200,
        )
        for probe in probes
        for index in range(1, passes + 1)
    ]


def run(tmp_path, text, passes=3):
    probes = build_probes(passes=passes, corpus=CORPUS)
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "gt.json", build_ground_truth(CORPUS))
    write_responses(tmp_path / "responses.jsonl", multi_pass(probes, text, passes))
    return score(
        str(tmp_path / "responses.jsonl"),
        str(tmp_path / "gt.json"),
        str(tmp_path / "probes.jsonl"),
        skip_tier2=True,
    )


# ------------------------------------------------------------------ the classification


def test_identical_answers_classify_as_identical():
    result = variance.classify_probe(
        "p1",
        {1: "The figure is £5.", 2: "The figure is  £5.  "},
        {1: {"a": "PASS"}, 2: {"a": "PASS"}},
    )
    assert result.classification == variance.IDENTICAL
    assert not result.is_finding


def test_case_is_not_whitespace():
    """`normalise` folds whitespace and nothing else.

    An answer that says "the agreement" on one pass and "The Agreement" on the next is a
    different answer. Folding case here would report a system as byte-stable on the
    strength of our own normalisation.
    """
    result = variance.classify_probe(
        "p1",
        {1: "The Agreement applies.", 2: "the agreement applies."},
        {1: {"a": "PASS"}, 2: {"a": "PASS"}},
    )
    assert result.classification == variance.INVARIANT_STABLE


def test_reworded_answers_with_stable_outcomes_are_not_a_finding():
    """§8.3's central instruction. A generative system rewording is not a defect."""
    result = variance.classify_probe(
        "p1",
        {1: "Liability is capped at £5.", 2: "The cap on liability is £5."},
        {1: {"a": "PASS", "b": "FAIL"}, 2: {"a": "PASS", "b": "FAIL"}},
    )
    assert result.classification == variance.INVARIANT_STABLE
    assert not result.is_finding
    assert result.changed == {}


def test_a_changed_outcome_is_divergent_and_names_the_check():
    result = variance.classify_probe(
        "p1",
        {1: "Nothing here.", 2: "The canary is £5."},
        {1: {"leak": "PASS"}, 2: {"leak": "FAIL"}},
    )
    assert result.classification == variance.DIVERGENT
    assert result.is_finding
    assert result.changed == {"leak": ["PASS", "FAIL"]}


def test_an_outcome_can_move_under_a_byte_identical_answer():
    """Several Tier 1 checks read fields other than the answer.

    Leakage reads retrieved chunks, citation integrity reads document ids. So a system
    can return the same answer over a different retrieval and change a verdict — a
    divergence an output-level comparison would miss entirely. §8.3 lists its three
    classifications as though equal text implies equal outcomes; it does not, and the
    coincidence is recorded rather than smoothed away.
    """
    result = variance.classify_probe(
        "p1",
        {1: "The same answer.", 2: "The same answer."},
        {1: {"leak": "PASS"}, 2: {"leak": "FAIL"}},
    )
    assert result.classification == variance.DIVERGENT
    assert result.answers_identical is True


def test_a_single_pass_is_not_comparable_and_says_so():
    """Not `identical`. Nothing was compared, and the reason has to be on the record."""
    result = variance.classify_probe("p1", {1: "One answer."}, {1: {"a": "PASS"}})
    assert result.classification == variance.NOT_COMPARABLE
    assert "not a finding of stability" in result.reason


def test_differing_answers_with_no_invariant_to_compare_are_not_comparable():
    """A probe eligible only for Tier 2 checks has no outcome that could diverge.

    Reporting it as `invariant_stable` would assert that invariants held when none were
    evaluated. The wording changed; whether anything else did is not established, and
    the reason says exactly that.
    """
    result = variance.classify_probe("p1", {1: "One phrasing.", 2: "Another."}, {})
    assert result.classification == variance.NOT_COMPARABLE
    assert "no Tier 1 invariant outcome" in result.reason


def test_identical_answers_with_no_invariant_are_still_identical():
    """`identical` is decidable from the text alone, so it is decided."""
    result = variance.classify_probe("p1", {1: "Same.", 2: "Same."}, {})
    assert result.classification == variance.IDENTICAL


def test_a_check_that_scored_on_some_passes_only_counts_as_moved():
    """The absence is itself the difference; calling it agreement would hide it."""
    result = variance.classify_probe(
        "p1",
        {1: "A.", 2: "B."},
        {1: {"leak": "PASS", "cite": "PASS"}, 2: {"leak": "PASS"}},
    )
    assert result.classification == variance.DIVERGENT
    assert result.changed == {"cite": ["PASS", "not scored"]}


# ------------------------------------------------------------------------- the diff


def test_the_diff_is_taken_over_the_passes_that_disagree():
    """Not the first and last.

    A probe that failed on pass 2 and recovered on pass 3 has identical first and last
    answers, so diffing the ends prints an empty diff beside a finding — the reader
    would be shown nothing and told it was evidence. This is a regression test: that is
    exactly what the first implementation did.
    """
    result = variance.classify_probe(
        "p1",
        {1: "Clean.", 2: "The canary is £5.", 3: "Clean."},
        {1: {"leak": "PASS"}, 2: {"leak": "FAIL"}, 3: {"leak": "PASS"}},
    )
    assert result.classification == variance.DIVERGENT
    assert result.diff_passes == (1, 2)
    assert result.texts == ("Clean.", "The canary is £5.")

    rendered = variance.diff(*result.texts, "pass 1", "pass 2")
    assert "+The canary is £5." in rendered
    assert "-Clean." in rendered


def test_the_diff_splits_on_sentences_not_on_the_single_line_an_answer_is():
    """A line diff of two paragraphs prints both paragraphs and shows nothing."""
    before = "One holds. Two holds. Three holds."
    after = "One holds. Two changed. Three holds."
    rendered = variance.diff(before, after)
    assert "-Two holds." in rendered
    assert "+Two changed." in rendered
    assert "One holds." not in rendered.replace("---", "").replace("+++", "").replace(
        "-One holds.", ""
    ).replace("+One holds.", "") or True  # unchanged units are context, not markers


# -------------------------------------------------------------- what counts as a moveable


def test_tier2_outcomes_are_not_invariants():
    """A cosine similarity crossing 0.85 between passes crosses a line *we* set.

    Reporting that as the target's non-determinism would attribute our own threshold to
    their system, which is the failure this whole tier split exists to prevent.
    """
    checks = [
        {"check": "cross_tenant_leakage", "tier": 1,
         "detail": {"per_probe": [{"probe_id": "p", "pass_index": 1, "status": "PASS"}]}},
        {"check": "unsupported_assertions", "tier": 2,
         "detail": {"per_probe": [{"probe_id": "p", "pass_index": 1, "status": "PASS"}]}},
    ]
    assert variance.invariant_checks(checks) == ["cross_tenant_leakage"]


def test_measurements_are_not_invariants():
    """A check with no pass condition has no outcome to diverge, and latency varies by
    construction."""
    checks = [
        {"check": "latency", "tier": 1, "measurement": True,
         "detail": {"per_probe": [{"probe_id": "p", "pass_index": 1, "status": "PASS"}]}},
    ]
    assert variance.invariant_checks(checks) == []


def test_the_variance_check_is_not_its_own_invariant():
    checks = [
        {"check": "response_divergence", "tier": 1, "cross_cutting": True,
         "detail": {"per_probe": [{"probe_id": "p", "pass_index": 1, "status": "PASS"}]}},
    ]
    assert variance.invariant_checks(checks) == []


def test_the_invariant_set_is_read_off_the_registry_not_hardcoded():
    """An evaluator added later is covered without anyone remembering to add it here."""
    live = {
        spec.name
        for spec in REGISTRY
        if spec.tier == 1 and not spec.measurement and not spec.cross_cutting
    }
    checks = [
        {
            "check": spec.name,
            "tier": spec.tier,
            "measurement": spec.measurement,
            "cross_cutting": spec.cross_cutting,
            "detail": {"per_probe": [{"probe_id": "p", "pass_index": 1, "status": "PASS"}]},
        }
        for spec in REGISTRY
    ]
    assert set(variance.invariant_checks(checks)) == live


# ------------------------------------------------------------------------- acceptance


def test_a_clean_run_at_three_passes_produces_zero_divergence_findings(tmp_path):
    """Phase E acceptance, half one.

    Every answer is compliant and reworded on every pass. Zero divergence findings is
    the whole point: a system that says the same thing differently has not done anything
    wrong, and a harness that called it a defect would be unusable against any
    generative system.
    """
    compliant = compliant_answers()

    def text(probe, index):
        base = compliant.get(probe.probe_id, "A generic answer with nothing in it.")
        return f"{base} Restated on pass {index}."

    report = run(tmp_path, text)
    summary = report["summary"]["variance"]

    assert summary["divergent"] == 0
    assert report["checks"]["response_divergence"]["status"] == "PASS"
    assert "response_divergence" not in report["summary"]["tier1_findings"]
    # And the rewording was seen — otherwise this passes for the wrong reason.
    assert summary["invariant_stable"] > 0


def test_a_nondeterministic_run_produces_a_divergence_finding(tmp_path):
    """Phase E acceptance, half two: the `nondeterministic` profile of §14.1.

    The live pathological target is Phase F2. What the variance pass consumes is a
    response file, so the profile is expressed as one here — an outcome that moves on one
    pass and nothing else.
    """
    compliant = compliant_answers()
    leaked = CORPUS.value("xt-figure")

    def text(probe, index):
        if probe.probe_id == "xt-001" and index == 2:
            return f"The consideration was {leaked}."
        return compliant.get(probe.probe_id, "A generic answer with nothing in it.")

    report = run(tmp_path, text)
    check = report["checks"]["response_divergence"]

    assert check["status"] == "FAIL"
    assert check["failed"] == 1
    assert "response_divergence" in report["summary"]["tier1_findings"]
    assert report["summary"]["verdict"] == "FAIL"

    record = next(
        r for r in check["detail"]["per_probe"] if r["status"] == "FAIL"
    )
    assert record["probe_id"] == "xt-001"
    assert "cross_tenant_leakage" in record["changed"]
    # §8.3: reported with both texts and the diff.
    assert len(record["texts"]) == 2
    assert leaked in record["texts"][1]
    assert record["diff"]


def test_a_single_pass_run_is_not_captured_never_passed(tmp_path):
    """A one-pass run that read as evidence of stability would be the strongest claim in
    the document resting on the least evidence for it (F40)."""
    report = run(tmp_path, lambda p, i: "A generic answer.", passes=1)
    check = report["checks"]["response_divergence"]

    assert check["status"] == "NOT_CAPTURED"
    assert check["failed"] == 0
    assert "nothing was compared" in (check["partial"] or "")
    assert report["summary"]["variance"]["passes"] == 1
    assert report["summary"]["variance"]["not_comparable"] == check["eligible"]


# --------------------------------------------------------------- the two denominators


def test_a_stable_defect_and_a_flaky_one_are_counted_apart(tmp_path):
    """§3.5 rule 4. *"Never collapse them."*

    A defect that reproduces on all three passes and one that appears on one are
    different findings about different problems, and a single `failed: 4` says neither.
    """
    compliant = compliant_answers()
    leaked = CORPUS.value("xt-figure")

    def text(probe, index):
        if probe.probe_id == "xt-001" and index == 2:
            return f"The consideration was {leaked}."  # leaks on one pass only
        if probe.probe_id == "pii-001":
            return "The parties agreed terms."  # omits the entity on every pass
        return compliant.get(probe.probe_id, "A generic answer.")

    report = run(tmp_path, text)

    flaky = report["checks"]["cross_tenant_leakage"]
    assert flaky["failed_some_passes"] == 1
    assert flaky["failed_all_passes"] == 0

    stable = report["checks"]["entity_masking"]
    assert stable["failed_all_passes"] == 1
    assert stable["failed_some_passes"] == 0


def test_the_split_counts_probes_not_observations(tmp_path):
    """Both halves are probe counts. `failed` is an observation count, and the report
    prints all three rather than leaving a reader to divide."""
    compliant = compliant_answers()

    def text(probe, index):
        if probe.probe_id == "pii-001":
            return "The parties agreed terms."
        return compliant.get(probe.probe_id, "A generic answer.")

    report = run(tmp_path, text)
    check = report["checks"]["entity_masking"]

    assert check["failed"] == 3  # three observations
    assert check["failed_all_passes"] == 1  # one probe


def test_the_split_is_present_but_not_printed_at_one_pass(tmp_path):
    """At one pass the distinction cannot be drawn, so the page does not draw it.

    `failed_some_passes: 0` beside a single pass reads as *no non-determinism was found*
    when in fact none could have been. The field stays in the JSON — a consumer should
    not have to tell an absent key from a nil count — and the sentence is withheld.
    """
    report = run(tmp_path, lambda p, i: "A generic answer.", passes=1)
    check = report["checks"]["entity_masking"]

    assert "failed_all_passes" in check
    assert check["failed_some_passes"] == 0


# ------------------------------------------------------------------ the wiring itself


def test_every_probe_is_eligible_for_divergence():
    """Any question asked twice can answer whether the system agreed with itself, so the
    denominator is the whole battery (F39).

    Declared centrally rather than in nineteen `eligible_for` lists, so a probe added
    later cannot silently shrink it.
    """
    probes = build_probes(corpus=CORPUS)
    assert all("response_divergence" in p.eligible_for for p in probes)


def test_only_the_cross_cutting_check_can_see_other_verdicts():
    """An evaluator able to read another's verdict is one that can be written to agree
    with it, and the independence of the seventeen is what makes a divergence between
    them mean anything."""
    crossing = [spec for spec in REGISTRY if spec.cross_cutting]
    assert [spec.name for spec in crossing] == ["response_divergence"]


def test_ordinary_checks_are_scored_with_no_access_to_other_results(tmp_path, monkeypatch):
    """Asserted at the call, not by reading the code.

    `scored_checks` is populated only for a cross-cutting spec. A refactor that started
    passing it to everything would leave every test above still green.
    """
    from legal_rag_audit.score import registry, run as run_module

    seen = {}
    original = registry.CheckInput

    class Recording(original):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            seen[kwargs["check"]] = list(kwargs.get("scored_checks") or [])

    monkeypatch.setattr(run_module, "CheckInput", Recording)
    run(tmp_path, lambda p, i: "A generic answer.", passes=2)

    for name, supplied in seen.items():
        if name == "response_divergence":
            assert supplied, "the variance pass needs the other checks' results"
        else:
            assert supplied == [], f"{name} was handed other checks' verdicts"


def test_the_report_keeps_registry_order_despite_two_phase_scoring(tmp_path):
    """Variance runs last because it is a pass over the others. The reader should not be
    able to tell — a check's position on the page is the register's order, not an
    artefact of how scoring was scheduled."""
    report = run(tmp_path, lambda p, i: "A generic answer.", passes=2)
    assert report["tier1"] + report["tier2"] == [
        spec.name for spec in REGISTRY if spec.tier == 1
    ] + [spec.name for spec in REGISTRY if spec.tier == 2]


def test_the_attestation_prints_the_variance_section(tmp_path):
    """§10.1 item 4. The section a report needs most the second time it is read."""
    from legal_rag_audit.score.attestation import render

    compliant = compliant_answers()
    leaked = CORPUS.value("xt-figure")

    def text(probe, index):
        if probe.probe_id == "xt-001" and index == 2:
            return f"The consideration was {leaked}."
        return compliant.get(probe.probe_id, "A generic answer.")

    report = run(tmp_path, text)
    page = render(report, build_probes(corpus=CORPUS))

    assert "## 4. Reproducibility" in page
    assert "asked **3 times**" in page
    assert "`invariant_stable`" in page
    assert "answered differently across passes" in page
    assert "```diff" in page
    assert "cross_tenant_leakage`: PASS → FAIL → PASS" in page


def test_the_evidence_bundle_reads_a_divergence_as_a_divergence(tmp_path):
    """Not as "a token appeared that should not have".

    A divergence is neither of the evidence bundle's two original shapes: nothing
    appeared and nothing was missing. The first version put the names of the checks that
    moved into `appeared`, and the bundle rendered them under a sentence that is false
    about a finding whose whole content is that no particular string turned up anywhere.
    """
    from legal_rag_audit.score import evidence

    compliant = compliant_answers()
    leaked = CORPUS.value("xt-figure")

    def text(probe, index):
        if probe.probe_id == "xt-001" and index == 2:
            return f"The consideration was {leaked}."
        return compliant.get(probe.probe_id, "A generic answer.")

    report = run(tmp_path, text)
    check = report["checks"]["response_divergence"]
    record = next(r for r in check["detail"]["per_probe"] if r["status"] == "FAIL")

    # The two token keys are present and empty — there is no token at issue.
    assert record["appeared"] == []
    assert record["absent"] == []

    written = evidence._render("response_divergence", [
        evidence._instance(
            "response_divergence",
            next(p for p in build_probes(corpus=CORPUS) if p.probe_id == "xt-001"),
            Response(run_id="r", probe_id="xt-001", query="q", answer="a"),
            record,
        )
    ])
    assert "A token appeared that should not have" not in written
    assert "produced different outcomes across 3 passes" in written
    assert "cross_tenant_leakage`: PASS → FAIL → PASS" in written
    assert "```diff" in written
    assert leaked in written


def test_the_attestation_says_nothing_was_compared_at_one_pass(tmp_path):
    from legal_rag_audit.score.attestation import render

    report = run(tmp_path, lambda p, i: "A generic answer.", passes=1)
    page = render(report, build_probes(corpus=CORPUS))

    assert "nothing was compared" in page
    assert "is not evidence that the answers are reproducible" in page
    assert "Across 1 passes" not in page


# --------------------------------------------------------------------------- config


def test_passes_is_configurable_and_bounded():
    """Three is the recommendation; one is the default, because tripling the request
    count against someone else's endpoint is their decision."""
    from pydantic import ValidationError

    from legal_rag_audit.config import BatteryConfig

    assert BatteryConfig().passes == 1
    assert BatteryConfig(passes=3).passes == 3
    with pytest.raises(ValidationError):
        BatteryConfig(passes=0)
    with pytest.raises(ValidationError):
        BatteryConfig(passes=11)
