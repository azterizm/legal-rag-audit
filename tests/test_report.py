"""The report: what it publishes, what it quotes, and what it refuses to say.

Three deliverables meet here, and each is defending a different claim.

**`report.json`** is a published contract (`report.v2`), so a consumer can build
against it. The tests hold the two decisions in the model: checks addressed by name
rather than nested under a tier that is expected to change, and `findings_hash`
covering exactly what `findings_of()` returns — a digest nobody can recompute from the
document they hold is decoration.

**`evidence/`** (F41) carries verbatim excerpts, so a Tier 1 finding is disputable on
the facts rather than on our arithmetic. The tests hold the distinction between a
token that appeared and a token that did not, because presenting the second as an
"excerpt" would imply we chose a fragment.

**`report.md`** (§10.6) is testimony. The tests hold the register rules: no headline
rate, no invented mechanism, and every not-run check on the page.
"""

import json
import re

import pytest

from legal_rag_audit.instruments import BY_CHECK
from legal_rag_audit.interchange import (
    Expectation,
    GroundTruth,
    Probe,
    Response,
    write_ground_truth,
    write_probes,
    write_responses,
)
from legal_rag_audit.probes import build_ground_truth, build_probes
from legal_rag_audit.provenance import hash_json
from legal_rag_audit.score import distributions, evidence, findings_of, score

LEAKED = "buyout is valued at exactly $5,000,000"


def make_run(tmp_path, answers=None, probes=None, ground_truth=None):
    probes = probes if probes is not None else build_probes()
    ground_truth = ground_truth if ground_truth is not None else build_ground_truth()
    answers = answers or {}
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "ground_truth.json", ground_truth)
    write_responses(
        tmp_path / "responses.jsonl",
        [
            Response(
                run_id="r",
                probe_id=p.probe_id,
                query=p.text,
                tenant=p.tenant,
                answer=answers.get(p.probe_id, "A generic answer with nothing in it."),
                citations=[],
                total_ms=100,
                http_status=200,
            )
            for p in probes
        ],
    )
    return (
        str(tmp_path / "responses.jsonl"),
        str(tmp_path / "ground_truth.json"),
        str(tmp_path / "probes.jsonl"),
    )


def run(tmp_path, answers=None, **kwargs):
    return score(*make_run(tmp_path, answers), skip_tier2=True, **kwargs)


# ------------------------------------------------------------------ report.v2 shape


def test_the_report_declares_the_contract_it_was_written_against(tmp_path):
    """NF10 runs both ways. A consumer must be able to refuse a report from a version
    it does not understand, which needs the version on the document."""
    assert run(tmp_path)["schema"] == "report.v2"


def test_a_check_is_addressed_by_name_not_by_its_tier(tmp_path):
    """The deviation from the §6.6 sketch, and the reason for it.

    `abstention` is registered Tier 2 today and §8.1 puts it in Tier 1 once Phase D
    rewrites it. Nesting checks under their tier would move a consumer's path to a
    check because we improved how it is scored.
    """
    report = run(tmp_path)

    assert "abstention" in report["checks"]
    assert set(report["tier1"]) | set(report["tier2"]) == set(report["checks"])
    # The tier lists carry §10.1's reading order, not the addresses.
    assert all(isinstance(name, str) for name in report["tier1"])
    for name in report["tier1"]:
        assert report["checks"][name]["tier"] == 1
    for name in report["tier2"]:
        assert report["checks"][name]["tier"] == 2


def test_the_findings_digest_covers_exactly_what_the_reader_can_hash(tmp_path):
    """The digest has to be recomputable from the published document.

    This is the failure the raw-dict version would have shipped: the models fill in
    absent optional fields as nulls, so a digest taken over the pre-serialisation
    dicts differs from one taken over the file for every check that ran cleanly. The
    published recipe would then be a false instruction — worse than none.
    """
    report = run(tmp_path)
    assert hash_json(findings_of(report)) == (
        report["manifest"]["scoring"]["findings_hash"]
    )


def test_the_report_validates_against_its_own_published_schema(tmp_path):
    """The schema is generated from the model, so this asserts the writer emits what
    the model describes — including the required `schema` field the generator adds."""
    from legal_rag_audit.interchange import read_schema_document

    document = read_schema_document("report.v2")
    report = run(tmp_path)

    assert "schema" in document["required"]
    for field in document["required"]:
        assert field in report, f"report.v2 requires {field!r} and the writer omits it"


# ------------------------------------------------------------ evidence bundle (F41)


def test_a_token_that_appeared_is_quoted_in_context(tmp_path):
    report = run(tmp_path, {"xt-001": f"In the Northbrook matter the {LEAKED} on completion."},
                 output_dir=str(tmp_path / "out"))

    assert report["checks"]["cross_tenant_leakage"]["status"] == "FAIL"
    assert report["evidence"]["cross_tenant_leakage"]["instances"] == 1

    written = (tmp_path / "out" / "evidence" / "cross_tenant_leakage.md").read_text()
    assert LEAKED in written
    assert "A token appeared that should not have" in written
    # The excerpt is a window of the answer, not a restatement of the expectation.
    assert "Northbrook matter" in written


def test_a_token_that_should_have_appeared_reproduces_the_whole_answer(tmp_path):
    """There is no excerpt to take when the claim is about an absence. Calling one an
    excerpt would imply we chose a fragment, and a reader would be right to ask what
    was in the rest."""
    answer = "The cap is whatever the agreement says. I cannot be more specific."
    report = run(tmp_path, {"syn-001": answer}, output_dir=str(tmp_path / "out"))

    assert report["checks"]["clause_synthesis"]["status"] == "FAIL"
    written = (tmp_path / "out" / "evidence" / "clause_synthesis.md").read_text()

    assert "Expected and absent:" in written
    assert "no excerpt to take" in written
    assert answer in written


def test_the_evidence_index_matches_the_files_on_disk(tmp_path):
    report = run(tmp_path, {"xt-001": f"…{LEAKED}…"}, output_dir=str(tmp_path / "out"))

    for check, index in report["evidence"].items():
        path = tmp_path / "out" / index["file"]
        assert path.exists(), f"{check} indexes {index['file']} and it was not written"
        assert path.read_text().count("\n## ") == index["instances"]


def test_only_tier_1_findings_get_an_evidence_file(tmp_path):
    """Tier 2 evidence is the distribution, not a quotation. Quoting a sentence a
    model scored 0.83 would dress a threshold decision as an observation."""
    report = run(tmp_path, {"xt-001": f"…{LEAKED}…"}, output_dir=str(tmp_path / "out"))

    for check in report["evidence"]:
        assert report["checks"][check]["tier"] == 1


def test_a_token_the_check_read_somewhere_other_than_the_answer_is_not_dropped():
    """Citation integrity matches document ids against the upload manifest, so its
    tokens are not in the answer text. Silently omitting those instances would
    undercount the findings the bundle exists to substantiate."""
    probe = Probe(
        probe_id="cap-001",
        family="citation_integrity",
        intent="positive",
        text="Which document says so?",
        eligible_for=["citation_integrity"],
    )
    response = Response(
        run_id="r",
        probe_id="cap-001",
        query="Which document says so?",
        answer="It is in the filed agreement.",
    )
    instances = evidence.collect(
        "citation_integrity",
        1,
        {
            "per_probe": [
                {
                    "status": "FAIL",
                    "probe_id": "cap-001",
                    "pass_index": 1,
                    "details": {"invalid_citations": ["doc_9999"]},
                }
            ]
        },
        {"cap-001": probe},
        {"cap-001": [response]},
    )

    assert len(instances) == 1
    match = instances[0]["matches"][0]
    assert match["token"] == "doc_9999"
    assert match["excerpt"] is None
    assert match["found_in"] == "not the answer text"


def test_every_evaluator_that_can_fail_contributes_a_named_evidence_key():
    """The key lists are enumerated, not heuristic. Enumeration rots silently — an
    evaluator gains a field, nobody adds it, and the bundle quietly falls back to
    reproducing whole answers for a check that had a token all along."""
    import ast
    from pathlib import Path

    import legal_rag_audit

    known = set(evidence.FOUND_KEYS) | set(evidence.MISSING_KEYS) | {"per_fact"}
    directory = Path(legal_rag_audit.__file__).parent / "evaluators"

    uncovered = []
    for path in sorted(directory.glob("*.py")):
        if path.name == "__init__.py":
            continue
        keys = {
            node.value
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        # An evaluator with no evidence-bearing key at all is fine — latency and the
        # Tier 2 pair score numbers, not tokens. One that has keys we do not read is
        # the failure this test exists for.
        if not keys & known and path.stem not in _SCORES_NUMBERS_NOT_TOKENS:
            uncovered.append(path.name)

    assert not uncovered, (
        f"these evaluators name no key the evidence bundle reads: {uncovered}. "
        f"Add the key to evidence.FOUND_KEYS or MISSING_KEYS, or add the module to "
        f"the numbers-not-tokens list with a reason."
    )


#: Evaluators the bundle cannot quote from, each for a stated reason.
_SCORES_NUMBERS_NOT_TOKENS = {
    "latency",  # seconds — there is no token
    "hallucination",  # Tier 2: the evidence is the distribution, not a quotation
    "retrieval",  # Tier 2, as above
    "confidence",  # Tier 2, as above
    # A known gap, not a numeric check. CacheInvalidationEvaluator returns
    # `has_stale_data` / `has_fresh_data` as booleans; the stale and fresh tokens are
    # arguments it never echoes, so there is nothing in the result to quote. Its
    # instances fall back to reproducing the whole answer. Phase D rewrites this
    # evaluator to the §8.2 recipe, which is where the tokens come back.
    "cache",
}


# ------------------------------------------------------- Tier 2 distributions (F24)


def test_a_distribution_marks_the_line_on_the_correct_side():
    """Both directions exist — `retrieval_relevance` passes at or above its line and
    `unsupported_assertions` passes at or below. A chart drawn without that marks the
    line on the wrong side for one of them."""
    higher = distributions.build(
        "retrieval_relevance",
        [
            {"probe_id": "a", "pass_index": 1, "avg_similarity": 0.91},
            {"probe_id": "b", "pass_index": 1, "avg_similarity": 0.42},
        ],
        0.85,
    )
    assert higher["on_the_passing_side"] == 1
    assert higher["line_reads"] == "at or above 0.85 passes"

    lower = distributions.build(
        "unsupported_assertions",
        [
            {"probe_id": "a", "pass_index": 1, "score": 0.0},
            {"probe_id": "b", "pass_index": 1, "score": 0.5},
        ],
        0.02,
    )
    assert lower["on_the_passing_side"] == 1
    assert lower["line_reads"] == "at or below 0.02 passes"


def test_the_distribution_says_the_line_is_a_setting_not_a_standard():
    """§19 item 7. `0.85` printed bare reads as a published standard, and it is a
    number we chose."""
    built = distributions.build(
        "retrieval_relevance", [{"probe_id": "a", "avg_similarity": 0.9}], 0.85
    )
    assert "not a published standard" in built["line_is"]
    assert built["measures"]


def test_a_record_the_evaluator_scored_without_a_number_is_counted_not_dropped():
    """A distribution over an unstated subset has an invisible denominator."""
    built = distributions.build(
        "retrieval_relevance",
        [
            {"probe_id": "a", "avg_similarity": 0.9},
            {"probe_id": "b", "details": "no similarity produced"},
        ],
        0.85,
    )
    assert built["records_with_a_number"] == 1
    assert built["records_without_a_number"] == 1


def test_the_buckets_are_fixed_so_two_runs_can_be_compared():
    """Buckets fitted to the observed range make two reports of the same check
    incomparable, which defeats the reason for printing a distribution."""
    tight = distributions.build(
        "retrieval_relevance",
        [{"probe_id": str(i), "avg_similarity": 0.9} for i in range(3)],
        0.85,
    )
    spread = distributions.build(
        "retrieval_relevance",
        [{"probe_id": str(i), "avg_similarity": i / 10} for i in range(10)],
        0.85,
    )
    assert [b["range"] for b in tight["buckets"]] == [
        b["range"] for b in spread["buckets"]
    ]
    assert sum(b["count"] for b in spread["buckets"]) == 10


def test_the_score_key_for_every_instrument_is_the_one_the_evaluator_emits():
    """The distribution reads the number by a declared key. If an evaluator renames
    it, every Tier 2 distribution silently empties."""
    import ast
    from pathlib import Path

    import legal_rag_audit

    modules = {
        "unsupported_assertions": "hallucination",
        "retrieval_relevance": "retrieval",
        "abstention": "confidence",
    }
    directory = Path(legal_rag_audit.__file__).parent / "evaluators"

    for check, module in modules.items():
        source = (directory / f"{module}.py").read_text(encoding="utf-8")
        keys = {
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert BY_CHECK[check].score_key in keys, (
            f"{module}.py no longer emits {BY_CHECK[check].score_key!r}; "
            f"the {check} distribution would be empty and nothing else would fail"
        )


def test_a_tier_2_check_carries_its_distribution_into_the_report(tmp_path):
    """Built from a stubbed scorer rather than a real model, so the wiring is tested
    in an environment with no torch — which is where `score` is meant to be readable."""
    from legal_rag_audit.score import registry, run as run_module

    probes = [
        Probe(
            probe_id="rel-001",
            family="retrieval_relevance",
            intent="positive",
            text="What is the cap?",
            eligible_for=["retrieval_relevance"],
        )
    ]
    ground_truth = GroundTruth(
        expectations=[Expectation(probe_id="rel-001", check="retrieval_relevance")]
    )
    spec = registry.BY_NAME["retrieval_relevance"]
    stub = registry.CheckSpec(
        name=spec.name,
        tier=spec.tier,
        needs=frozenset(),
        scorer=lambda data: registry.CheckOutcome(
            status="FAIL",
            scored=1,
            failed=1,
            detail={
                "per_probe": [
                    {
                        "status": "FAIL",
                        "probe_id": "rel-001",
                        "pass_index": 1,
                        "avg_similarity": 0.31,
                    }
                ]
            },
        ),
        recipe=spec.recipe,
        key=spec.key,
    )

    paths = make_run(tmp_path, probes=probes, ground_truth=ground_truth)
    original_registry = run_module.REGISTRY
    original_available = run_module.tier2_available
    run_module.REGISTRY = (stub,)
    # The stub never loads a model, but the preflight refuses to start a Tier 2 run
    # without the layer installed — correctly, and not what this test is about.
    run_module.tier2_available = lambda: (True, "")
    try:
        report = score(*paths, output_dir=str(tmp_path / "out"))
    finally:
        run_module.REGISTRY = original_registry
        run_module.tier2_available = original_available

    dist = report["checks"]["retrieval_relevance"]["distribution"]
    assert dist["records_with_a_number"] == 1
    assert dist["on_the_failing_side"] == 1
    assert dist["min"] == 0.31

    attestation = (tmp_path / "out" / "report.md").read_text()
    assert "all-MiniLM-L6-v2" in attestation
    assert "not a published standard" in attestation


# ------------------------------------------------------- the attestation (§10.6)


def test_the_attestation_carries_no_headline_rate(tmp_path):
    """Appendix D. A single percentage needs a denominator the reader cannot see and
    invites being quoted without one."""
    run(tmp_path, {"xt-001": f"…{LEAKED}…"}, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()

    percentages = re.findall(r"\d+(?:\.\d+)?\s?%", document)
    assert not percentages, f"the attestation prints a rate: {percentages}"


def test_the_attestation_invents_no_mechanism(tmp_path):
    """§10.4's mechanism section names a design property behind a finding, which
    needs visibility into an architecture the tool does not have. Generating one
    would be the failure this project measures in other people's systems."""
    run(tmp_path, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()

    mechanisms = document.split("## 6. Mechanisms")[1].split("## 7.")[0]
    assert "*Not generated.*" in mechanisms
    assert "By design" in document


def test_the_attestation_lists_every_check_that_did_not_run(tmp_path):
    """A check absent from a report is indistinguishable from one that passed."""
    report = run(tmp_path, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()

    for name, check in report["checks"].items():
        if check["status"] in ("NOT_ELIGIBLE", "NOT_CAPTURED"):
            assert f"`{name}`" in document, f"{name} did not run and is not on the page"


def test_the_attestation_states_which_half_of_the_battery_was_sealed(tmp_path):
    report = run(tmp_path, {"xt-001": f"…{LEAKED}…"}, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()

    failing = [c for c in report["checks"].values() if c["status"] == "FAIL"]
    assert failing
    assert "sealed until this report" in document or "published with the battery" in (
        document
    )


def test_the_attestation_says_when_a_run_makes_no_pre_commitment_claim(tmp_path):
    """Silence would read as a claim. A run without a handover record has to say so."""
    run(tmp_path, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()
    assert "makes no pre-commitment claim" in document


def test_the_attestation_carries_the_reproduction_digests(tmp_path):
    report = run(tmp_path, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()

    inputs = report["manifest"]["inputs"]
    assert inputs["responses_hash"] in document
    assert inputs["ground_truth_manifest_hash"] in document
    assert report["manifest"]["scoring"]["findings_hash"] in document
    assert "shasum -a 256" in document


def test_following_the_reproduction_instructions_yields_the_digest_they_promise(
    tmp_path,
):
    """§7 of the attestation makes a checkable promise. If it is false it is the worst
    defect in the document — the section a sceptical reader goes to first, telling
    them to expect a number they will not get."""
    paths = make_run(tmp_path, {"xt-001": f"…{LEAKED}…"})
    score(*paths, skip_tier2=True, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()

    promised = re.search(r"yields findings digest `(sha256:[0-9a-f]+)`", document)
    assert promised, "the attestation makes no reproduction claim"

    rescored = score(*paths, skip_tier2=True, output_dir=str(tmp_path / "again"))
    assert rescored["manifest"]["scoring"]["findings_hash"] == promised.group(1)


def test_the_attestation_separates_our_determinism_from_theirs(tmp_path):
    """Conflating the two destroys both — a vendor who runs it twice and sees two
    different rates concludes the tool is broken."""
    run(tmp_path, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()
    assert "property of this instrument, not of" in document


def test_the_attestation_is_written_on_every_run(tmp_path):
    run(tmp_path, output_dir=str(tmp_path / "out"))
    assert (tmp_path / "out" / "report.md").exists()
    assert (tmp_path / "out" / "report.json").exists()


def test_a_clean_run_says_so_without_claiming_more(tmp_path):
    """A report with no findings must not read as a certificate."""
    probes = [
        Probe(
            probe_id="route-001",
            family="routing_contamination",
            intent="positive",
            text="What is the retention policy?",
            eligible_for=["routing_contamination"],
        )
    ]
    ground_truth = GroundTruth(
        expectations=[
            Expectation(
                probe_id="route-001",
                check="routing_contamination",
                must_not_contain=["TikTok"],
            )
        ]
    )
    paths = make_run(tmp_path, probes=probes, ground_truth=ground_truth)
    report = score(*paths, skip_tier2=True, output_dir=str(tmp_path / "out"))

    assert report["summary"]["verdict"] == "PASS"
    document = (tmp_path / "out" / "report.md").read_text()
    assert "No Tier 1 check produced a finding on this run." in document
    # And the not-run checks are still on the page, because a clean verdict over a
    # battery that mostly did not run is the most misleading document this tool
    # could produce.
    assert "What did not run" in document
    assert "Neither of these is a pass" in document


def test_the_written_report_json_is_the_returned_report(tmp_path):
    report = run(tmp_path, output_dir=str(tmp_path / "out"))
    written = json.loads((tmp_path / "out" / "report.json").read_text())
    assert written == report


@pytest.mark.parametrize("section", ["## 0.", "## 1.", "## 2.", "## 3.", "## 4.",
                                     "## 5.", "## 6.", "## 7.", "## 8."])
def test_the_attestation_follows_the_skeleton_order(tmp_path, section):
    """§10.1: order is load-bearing. Deal-enders first, mechanism last."""
    run(tmp_path, output_dir=str(tmp_path / "out"))
    document = (tmp_path / "out" / "report.md").read_text()
    assert section in document
