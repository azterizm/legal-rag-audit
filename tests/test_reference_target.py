"""Phase F2 — sensitivity and specificity of the harness (V2_FULL_PLAN.md §14).

The objection after *"is it safe"* is *"how do I know your tool is right?"* These are the
two numbers that answer it, and both are about our instrument rather than anybody's
product:

* **Sensitivity** — every registered check, given a target exhibiting the defect it looks
  for, reports it. The gate is written against `score.registry` rather than a hardcoded
  count, so shipping an evaluator without a pathology profile fails the build instead of
  quietly shrinking the denominator (§14.2).
* **Specificity** — the `clean` profile, at three passes, produces no findings at all.
  §14.2 makes a false positive a release blocker, and this is where one would surface.

**Every run here is a full run.** Corpus planted to disk, uploaded over HTTP, answered by
a server that has only the probe file and what arrived at `/upload`, captured through the
transport client's JSONPaths, written to `responses.jsonl`, scored offline against a key
built from the same seed. Phase E's variance acceptance was met against response files
because the reference target did not exist yet; here it is met against a live target,
which is the deviation that phase recorded and this one closes.

**Two things the gate asserts that §14.2 does not ask for**, both because a green
sensitivity number is worth less without them:

* *A pathology fails only what it claims.* A profile that tripped six checks would make
  the matrix meaningless — the reader could not tell which evaluator caught what. Every
  side effect is declared on the profile in `also_trips` rather than tolerated.
* *The mock cannot see the answer key.* Its imports are checked. An oracle that answered
  out of `ground_truth.json` would make the clean run a test that the scorer agrees with
  itself.
"""

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from legal_rag_audit.config import AuditConfig
from legal_rag_audit.evaluators.latency import SUGGESTIVE_GAP_RATIO
from legal_rag_audit.generate import generate
from legal_rag_audit.interchange import write_ground_truth, write_probes
from legal_rag_audit.plants import plant, write_corpus
from legal_rag_audit.probes import BATTERY, build_ground_truth, build_probes
from legal_rag_audit.score import score
from legal_rag_audit.score.registry import BY_NAME as CHECKS
from legal_rag_audit.score.registry import REGISTRY
from legal_rag_audit.score.run import tier2_available
from mock_target import BY_NAME as PROFILE
from mock_target import CLEAN, PROFILES, Profile, answered_probe_ids, serve

REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = Path(__file__).resolve().parent / "mock_target"
MATRIX = REPO_ROOT / "docs" / "harness-verification.md"

#: Fixed, so every profile runs against the same corpus and a failure is about the
#: profile rather than about which invariants the seed happened to mint. Not the
#: published demo seed: a gate that only holds for one corpus is not a gate.
SEED = "legal-rag-audit/reference-target/v2"


# --------------------------------------------------------------------- running one


@dataclass
class Run:
    profile: Profile
    report: dict
    uploaded: list[str]
    unknown_queries: list[str]


def _config(work: Path, endpoints: dict[str, str], passes: int) -> Path:
    path = work / "config.yaml"
    path.write_text(
        "target:\n"
        "  name: reference-target\n"
        "  endpoints:\n"
        f"    chat: {endpoints['chat']}\n"
        f"    upload: {endpoints['upload']}\n"
        f"    retrieval: {endpoints['retrieval']}\n"
        "  auth:\n"
        "    type: none\n"
        "  response_format:\n"
        "    answer_field: response.text\n"
        "    citations_field: response.sources\n"
        "corpus:\n"
        "  mode: planted\n"
        # Zero, and the report says so beside the freshness finding. A mock invalidates
        # its index the instant the document arrives, so a wait would measure nothing
        # except how patient the test suite is.
        "  revision_wait_seconds: 0\n"
        "battery:\n"
        f"  passes: {passes}\n",
        encoding="utf-8",
    )
    return path


def _execute(work: Path, profile: Profile, tier2: bool) -> Run:
    work.mkdir(parents=True, exist_ok=True)

    corpus = plant(SEED)
    corpus_root = work / "corpus"
    write_corpus(corpus_root, corpus)
    probes = build_probes(passes=profile.passes, corpus=corpus)
    probes_path = work / "probes.jsonl"
    write_probes(probes_path, probes)
    ground_truth_path = work / "ground_truth.json"
    write_ground_truth(ground_truth_path, build_ground_truth(corpus))

    responses_path = work / "responses.jsonl"
    with serve(profile, probes) as running:
        config_path = _config(work, running.endpoints(), profile.passes)
        generate(
            config=AuditConfig.load_from_yaml(str(config_path)),
            responses_path=str(responses_path),
            passes=profile.passes,
            corpus_dir=str(corpus_root),
            probes_in=str(probes_path),
        )
        uploaded = running.uploaded
        unknown = running.unknown_queries

    # After the server is down, so `offline()` cannot be satisfied by a socket this test
    # happens to have left open. The engagement's shape as well: score never runs while
    # anything is still talking to the target.
    report = score(
        str(responses_path),
        str(ground_truth_path),
        str(probes_path),
        skip_tier2=not tier2,
        config_path=str(config_path),
    )
    return Run(profile=profile, report=report, uploaded=uploaded, unknown_queries=unknown)


class _Runs:
    """Every profile run at most once per session, and reused."""

    def __init__(self, root: Path):
        self.root = root
        self._cache: dict[tuple[str, bool], Run] = {}

    def get(self, profile: Profile, tier2: bool = False) -> Run:
        key = (profile.name, tier2)
        if key not in self._cache:
            suffix = "-tier2" if tier2 else ""
            self._cache[key] = _execute(
                self.root / f"{profile.name}{suffix}", profile, tier2
            )
        return self._cache[key]


@pytest.fixture(scope="session")
def runs(tmp_path_factory):
    return _Runs(tmp_path_factory.mktemp("reference-target"))


def _findings(report: dict) -> set[str]:
    summary = report["summary"]
    return set(summary["tier1_findings"]) | set(summary["tier2_findings"])


def _needs_tier2(profile: Profile) -> bool:
    return any(CHECKS[name].tier == 2 for name in profile.detects)


TIER1_PROFILES = [p for p in PROFILES if p.detects and not _needs_tier2(p)]
TIER2_PROFILES = [p for p in PROFILES if p.detects and _needs_tier2(p)]


def _detected(report: dict, name: str) -> tuple[bool, str]:
    """Whether the check noticed, and what it saw.

    Detection is `FAIL` for a check with a pass condition. `latency` has none by design
    (§8.2 #15) — a threshold there would be ours rather than a standard, so the measure
    cannot fail and the gate would be unsatisfiable if it demanded that it did. What it
    can do is produce the paired reading, and that reading firing is the detection. The
    branch is taken off `spec.measurement` rather than off the check's name, so a second
    measurement added later is covered without anyone remembering this.
    """
    check = report["checks"][name]
    if not CHECKS[name].measurement:
        return check["status"] == "FAIL", check["status"]
    inference = (check.get("detail") or {}).get("inference") or {}
    ratio = inference.get("total_ratio")
    return (
        ratio is not None and ratio >= SUGGESTIVE_GAP_RATIO,
        f"total_ratio={ratio}",
    )


# ----------------------------------------------------------- the register is closed


def test_every_registered_check_is_claimed_by_a_profile():
    """§14.2's *no exemptions*, mechanised.

    The denominator of the sensitivity number is the registry, so a check can never
    leave it by nobody writing a profile. Shipping an evaluator without one fails here
    rather than shrinking the claim silently.
    """
    claimed = {name for profile in PROFILES for name in profile.detects}
    registered = {spec.name for spec in REGISTRY}
    assert claimed == registered, (
        f"checks with no pathology profile: {sorted(registered - claimed)}; "
        f"profiles naming a check that is not registered: {sorted(claimed - registered)}"
    )


def test_the_profile_set_is_the_one_the_plan_names():
    """§14.1's table, minus the row whose evaluator has not shipped."""
    assert [p.name for p in PROFILES] == [
        "leak_tenant_b",
        "follow_injection",
        "fabricate_citations",
        "stale_index",
        "swap_counterparties",
        "parametric_answer",
        "ignore_namespace",
        "pick_one_silently",
        "merge_sources",
        "drop_exclusion",
        "naive_chunking",
        "collide_articles",
        "wrong_referent",
        "slow_regenerate",
        "unsupported_prose",
        "irrelevant_chunks",
        "nondeterministic",
        "clean",
    ]
    assert "serve_licensed_content" not in {p.name for p in PROFILES}, (
        "the licensed-content profile arrives in Phase G with evaluator #18; a profile "
        "for a check that does not exist would be a matrix row that can never go green"
    )


def test_the_reference_target_answers_every_probe_in_the_battery():
    """A probe the mock cannot answer would be scored as the target failing to."""
    assert answered_probe_ids() == {entry.probe_id for entry in BATTERY}


def test_the_reference_target_cannot_read_the_answer_key():
    """Its imports, checked. The clean run means nothing if the oracle can cheat.

    The mock is allowed the probe file — the target is given that — and the templates,
    which are the *shape* of the documents rather than their contents. Everything else
    it knows arrived at `/upload`. An import of `interchange.ground_truth`, `probes`, or
    `plants.pipeline` would let it answer out of the key it is supposed to be tested
    against, and the specificity gate would become a tautology.
    """
    allowed = {
        "legal_rag_audit.interchange.probe",
        "legal_rag_audit.plants.templates",
    }
    for path in sorted(MOCK_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module)
        reached = {name for name in imported if name.startswith("legal_rag_audit")}
        assert reached <= allowed, (
            f"{path.relative_to(REPO_ROOT)} imports {sorted(reached - allowed)}. The "
            f"reference target answers from the corpus it was uploaded, never from the "
            f"ground truth it is being scored against."
        )


# ------------------------------------------------------------------- sensitivity


@pytest.mark.parametrize("profile", TIER1_PROFILES, ids=lambda p: p.name)
def test_sensitivity(runs, profile):
    """Each pathology on ⇒ the check that looks for it reports it."""
    report = runs.get(profile).report
    for name in profile.detects:
        detected, saw = _detected(report, name)
        assert detected, (
            f"profile {profile.name!r} exhibits {profile.behaviour.lower()}, and "
            f"{name} did not notice: {saw}"
        )


@pytest.mark.parametrize("profile", TIER1_PROFILES, ids=lambda p: p.name)
def test_a_pathology_fails_only_what_it_claims(runs, profile):
    """One deliberate defect per profile, and the side effects are declared.

    Without this the sensitivity number would survive a mock that answered every probe
    badly: sixteen green rows, and no evidence that any evaluator caught the thing it
    was pointed at rather than the noise around it.
    """
    allowed = set(profile.detects) | set(profile.also_trips)
    unexpected = _findings(runs.get(profile).report) - allowed
    assert not unexpected, (
        f"profile {profile.name!r} also failed {sorted(unexpected)}, which it does not "
        f"claim. Either the pathology is wider than it says, or a check is firing on "
        f"something it should not."
    )


#: The Tier 2 rows load checkpoints resolved by name, so the first run fetches several
#: hundred megabytes from a third party. Opt-in, and set in exactly one CI job rather
#: than on every matrix entry of every push: a release pipeline built to eliminate
#: mutable references should not acquire one by downloading unpinned weights three times
#: a commit. Where it is not set the rows skip and **name the checks they did not
#: verify**, because a gate that narrows itself quietly is the defect it exists to catch.
TIER2_GATE_ENV = "LEGAL_RAG_AUDIT_TIER2_GATE"


@pytest.mark.slow
@pytest.mark.parametrize("profile", TIER2_PROFILES, ids=lambda p: p.name)
def test_sensitivity_tier2(runs, profile):
    """The two model-backed checks, against the same reference target."""
    checks = ", ".join(profile.detects)
    if os.environ.get(TIER2_GATE_ENV) != "1":
        pytest.skip(
            f"{checks} was not verified here: the Tier 2 rows fetch unpinned model "
            f"weights, so they run only where {TIER2_GATE_ENV}=1"
        )
    available, why = tier2_available()
    if not available:
        pytest.skip(
            f"the Tier 2 scoring layer is not installed, so {checks} was not "
            f"verified here: {why}"
        )
    report = runs.get(profile, tier2=True).report
    for name in profile.detects:
        detected, saw = _detected(report, name)
        assert detected, f"{profile.name}: {name} did not notice ({saw})"


# ------------------------------------------------------------------- specificity


def test_specificity_the_clean_target_produces_no_findings(runs):
    """§14.2's release blocker. Three passes, zero findings, Tier 1."""
    report = runs.get(CLEAN).report
    assert _findings(report) == set()
    assert report["summary"]["verdict"] == "PASS"


def test_specificity_every_check_passed_or_did_not_apply(runs):
    """`PASS` or `NOT_ELIGIBLE` — never `NOT_CAPTURED`, which is not a pass either.

    Tier 2 is excluded here because this run scored with `--skip-tier2`, which reports
    those two as not run; `test_sensitivity_tier2` covers them where the layer exists.
    """
    report = runs.get(CLEAN).report
    for name, check in report["checks"].items():
        if CHECKS[name].tier == 2:
            continue
        assert check["status"] in ("PASS", "NOT_ELIGIBLE"), (
            f"{name} is {check['status']} on a target known to be correct: "
            f"{check.get('reason') or check.get('partial')}"
        )


def test_the_clean_run_reached_the_target_cleanly(runs):
    """No transport error, no unrecognised query, every document accepted.

    A clean report over a run where half the requests failed would be `NOT_CAPTURED`
    everywhere and would still show zero findings. This is what separates the two.
    """
    run = runs.get(CLEAN)
    assert run.unknown_queries == [], (
        "the reference target did not recognise a query; the battery and the mock have "
        "moved apart"
    )
    assert run.report["capture"]["transport_errors"] == 0
    assert run.report["capture"]["citations_captured"] is True
    assert run.report["capture"]["retrieved_chunks_captured"] is True
    assert run.report["capture"]["document_ids_supplied"] is True
    # Fourteen base documents and the revised retainer notice.
    assert len(run.uploaded) == 15


def test_the_clean_run_agrees_with_itself_across_three_passes(runs):
    """Phase E's second acceptance, re-run against a live target.

    Zero divergent findings is only half of it. A run where nothing could be compared
    would also report zero, so the positive count is asserted too — the same reason
    `not_comparable` exists as a fourth classification (§8.3).
    """
    variance = runs.get(CLEAN).report["summary"]["variance"]
    assert variance["passes"] == 3
    assert variance["divergent"] == 0
    assert variance["identical"] + variance["invariant_stable"] == len(BATTERY)
    assert variance["status"] == "PASS"


def test_the_clean_run_does_not_produce_the_latency_reading(runs):
    """The paired inference is a finding-shaped sentence, and it must not fire here.

    It never reaches the findings table — latency is a measurement — but a mechanism
    section telling a client their system regenerates answers, on a target that does
    nothing of the sort, is a false positive in every sense that matters commercially.
    """
    detected, saw = _detected(runs.get(CLEAN).report, "latency")
    assert not detected, f"the catch-and-regenerate reading fired on a clean target: {saw}"


def test_one_moved_outcome_produces_exactly_one_divergence_finding(runs):
    """Phase E's first acceptance, re-run against a live target.

    The count matters as much as the finding: a variance pass that reported every probe
    as divergent whenever any of them was would be useless for triage, and the profile
    moves exactly one outcome on exactly one pass.
    """
    report = runs.get(PROFILE["nondeterministic"]).report
    divergence = report["checks"]["response_divergence"]
    assert divergence["status"] == "FAIL"
    assert divergence["failed"] == 1
    changed = [
        record
        for record in divergence["detail"]["per_probe"]
        if record["status"] == "FAIL"
    ]
    assert [record["probe_id"] for record in changed] == ["disamb-001"]
    assert "disambiguation" in changed[0]["changed"]


# ------------------------------------------------------- the published matrix


def _matrix_rows() -> dict[str, dict[str, str]]:
    """The profile table in `docs/harness-verification.md`, parsed."""
    rows: dict[str, dict[str, str]] = {}
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*`([a-z_]+)`\s*\|(.*)\|\s*$", line)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(2).split("|")]
        rows[match.group(1)] = {
            "behaviour": cells[0],
            "detects": cells[1],
        }
    return rows


def test_the_published_matrix_describes_the_profiles_that_exist():
    """§14.2 calls the matrix a credibility artefact. A stale one is the opposite.

    Same discipline as `docs/responses-schema.md`: the document is checked against the
    code rather than maintained beside it, because a published claim about our own
    instrument that nobody re-derives is exactly the kind we tell clients not to accept.
    """
    rows = _matrix_rows()
    assert set(rows) == {p.name for p in PROFILES}, (
        f"in the matrix but not in the code: {sorted(set(rows) - {p.name for p in PROFILES})}; "
        f"in the code but not in the matrix: {sorted({p.name for p in PROFILES} - set(rows))}"
    )
    for profile in PROFILES:
        row = rows[profile.name]
        assert row["behaviour"] == profile.behaviour, (
            f"{profile.name}: the matrix describes it as {row['behaviour']!r}, the code "
            f"as {profile.behaviour!r}"
        )
        named = {name.strip(" `") for name in row["detects"].split(",") if name.strip()}
        expected = set(profile.detects) or {"—"}
        assert named == expected, (
            f"{profile.name}: the matrix says it fires {sorted(named)}, the code says "
            f"{sorted(expected)}"
        )


def test_the_matrix_states_what_the_two_numbers_do_not_establish():
    """A published number about our own instrument carries its own limit (§3.3)."""
    text = MATRIX.read_text(encoding="utf-8")
    assert "does not establish" in text or "do not establish" in text
