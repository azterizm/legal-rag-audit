"""`score` — read a response file and a ground-truth manifest, write a report.

Offline, and enforced rather than promised (§5.1, F18). Nothing here imports the
transport package; a test asserts that no module reachable from `score` can, and
`enforce_offline()` makes an attempt raise even if one day something does.

The work this module does that the evaluators do not: deciding, for each check,
*whether it ran at all*. Four statuses, and the distinction between the last two is the
whole reason F40 exists:

* `PASS` — scored, nothing failed.
* `FAIL` — scored, something failed.
* `NOT_ELIGIBLE` — no probe in the probe file was declared eligible. The check does not
  apply to this deployment. A single-tenant system has no cross-tenant leakage to find,
  and reporting that as a pass would be a clean result nobody earned.
* `NOT_CAPTURED` — probes were eligible, but the response file does not carry what the
  check reads. The check did not run. It is not a pass.

Denominators come from the probe file's `eligible_for`, declared before the run, never
from what the results turned out to be (F39, §3.5 rule 3).
"""

import logging
from collections import defaultdict
from contextlib import nullcontext
from typing import Any, Optional

from ..config import ThresholdsConfig
from ..instruments import BY_CHECK, threshold_for
from ..interchange import (
    GroundTruth,
    PreCommitment,
    Probe,
    Report,
    Response,
    ResponseFile,
    build_findings,
    load_ground_truth,
    load_handover,
    load_probes,
    load_responses,
    now_utc,
)
from ..provenance import build_run_manifest, verify_pre_commitment
from . import distributions, evidence
from .offline import offline
from .output import write_bundle
from .registry import (
    ANSWER,
    BY_NAME,
    CAPABILITY_HELP,
    CITATIONS,
    DOCUMENT_IDS,
    REGISTRY,
    RETRIEVED_CHUNKS,
    TIMING,
    CheckInput,
    CheckSpec,
)

logger = logging.getLogger(__name__)

PASS = "PASS"
FAIL = "FAIL"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
NOT_CAPTURED = "NOT_CAPTURED"


class ScoringError(Exception):
    """The run could not be scored. A setup problem, not a finding (NF9)."""


def _by_probe(responses: list[Response]) -> dict[str, list[Response]]:
    grouped: dict[str, list[Response]] = defaultdict(list)
    for response in responses:
        grouped[response.probe_id].append(response)
    for records in grouped.values():
        records.sort(key=lambda r: r.pass_index)
    return dict(grouped)


def _missing_capabilities(
    spec: CheckSpec,
    probes: list[Probe],
    grouped: dict[str, list[Response]],
    response_file: ResponseFile,
) -> list[str]:
    """Capabilities the check needs that this response file does not carry.

    Judged over the eligible probes only. A file that captured chunks for some probes
    and not others is not "missing chunks" for a check whose own probes have them.
    """
    records = [r for p in probes for r in grouped.get(p.probe_id, [])]
    usable = [r for r in records if r.usable]
    missing = []

    if ANSWER in spec.needs and not usable:
        missing.append(ANSWER)
    if CITATIONS in spec.needs and not any(r.citations is not None for r in usable):
        missing.append(CITATIONS)
    if RETRIEVED_CHUNKS in spec.needs and not any(
        r.retrieved_chunks is not None for r in usable
    ):
        missing.append(RETRIEVED_CHUNKS)
    if DOCUMENT_IDS in spec.needs and not (
        response_file.capture_notes and response_file.capture_notes.document_ids
    ):
        missing.append(DOCUMENT_IDS)
    if TIMING in spec.needs and not any(r.total_ms is not None for r in usable):
        missing.append(TIMING)

    return missing


def score_check(
    spec: CheckSpec,
    probes: list[Probe],
    response_file: ResponseFile,
    ground_truth: GroundTruth,
    thresholds: ThresholdsConfig,
    skipped: bool = False,
) -> dict[str, Any]:
    """Score one check, or say why it did not run."""
    eligible = [p for p in probes if spec.name in p.eligible_for]
    result: dict[str, Any] = {
        "check": spec.name,
        "tier": spec.tier,
        # Whether this check's expectation was published with the battery or sealed
        # until the report (§3.6.1). On the page, because a reader is entitled to know
        # which half of the battery the target could see in advance — and because the
        # answer for two checks depends on what the response file carried.
        "key": spec.key_for(bool(response_file.retrieved_chunks_captured())),
        "recipe": spec.recipe,
        "eligible": len(eligible),
        "scored": 0,
        "not_captured": 0,
        "failed": 0,
    }

    if not eligible:
        result["status"] = NOT_ELIGIBLE
        result["reason"] = (
            "no probe in the probe file declares this check in `eligible_for`, so it "
            "does not apply to this run"
        )
        return result

    if skipped:
        # Deliberately not run. Reported rather than omitted: a check absent from the
        # report is indistinguishable from one that passed, which is the failure mode
        # F40 exists to prevent.
        result["status"] = NOT_CAPTURED
        result["not_captured"] = len(eligible)
        result["reason"] = (
            "Tier 2 scoring was disabled for this run (--skip-tier2), so this check "
            "did not execute. It is not a pass"
        )
        return result

    grouped = _by_probe(response_file.responses)
    records = [r for p in eligible for r in grouped.get(p.probe_id, [])]
    unusable = [r for r in records if not r.usable]
    result["not_captured"] = len(unusable) + sum(
        1 for p in eligible if not grouped.get(p.probe_id)
    )

    missing = _missing_capabilities(spec, eligible, grouped, response_file)
    if missing:
        result["status"] = NOT_CAPTURED
        result["reason"] = "the response file does not carry " + "; ".join(
            CAPABILITY_HELP[m] for m in missing
        )
        result["not_captured"] = len(eligible)
        return result

    outcome = spec.scorer(
        CheckInput(
            check=spec.name,
            probes=eligible,
            responses=grouped,
            expectations=ground_truth.for_check(spec.name),
            document_ids=(
                response_file.capture_notes.document_ids
                if response_file.capture_notes
                else None
            ),
            thresholds=thresholds,
        )
    )

    result["status"] = outcome.status
    result["scored"] = outcome.scored
    result["failed"] = outcome.failed
    result["detail"] = outcome.detail
    if outcome.partial:
        result["partial"] = outcome.partial

    # F24. A Tier 2 verdict without its distribution hides how close to the line every
    # record sat, and hides that the line is a setting of ours rather than a standard.
    if spec.name in BY_CHECK:
        result["distribution"] = distributions.build(
            spec.name,
            outcome.detail.get("per_probe", []),
            threshold_for(spec.name, thresholds),
        )

    if outcome.scored == 0 and outcome.status != FAIL:
        # Eligible, capable, and nothing was actually compared. That is not a pass.
        result["status"] = NOT_CAPTURED
        result.setdefault(
            "reason", outcome.partial or "no record could be scored for this check"
        )

    return result


def tier2_available() -> tuple[bool, str]:
    """Whether the Tier 2 layer is installed, and why not if it is not."""
    try:
        import sentence_transformers  # noqa: F401
    except ImportError as e:
        return False, str(e)
    return True, ""


def score(
    responses_path: str,
    ground_truth_path: str,
    probes_path: Optional[str] = None,
    thresholds: Optional[ThresholdsConfig] = None,
    enforce: bool = True,
    skip_tier2: bool = False,
    config_path: Optional[str] = None,
    handover_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Score a run. Returns the report body.

    `probes_path` is optional only because a response file records the probes it
    answered; when it is absent, eligibility is reconstructed from the ground truth,
    which is weaker and the report says so.

    `handover_path` turns the pre-commitment of §3.6 from an undertaking into a
    precondition: the digests published before the run are recomputed here, and a
    ground truth that has moved since aborts the run.

    `output_dir` is where the report, the manifest and the disclosed ground truth are
    written. A caller that wants only the dict may leave it out; the CLI never does,
    because F44 makes disclosure a property of the tool.

    Network enforcement is scoped to this call. It is on for every line of scoring and
    off when the call returns, so importing this function does not leave a caller's
    process unable to open a socket. `enforce=False` is for a caller that has already
    entered `offline()` around a wider region.
    """
    with offline() if enforce else nullcontext():
        return _score(
            responses_path,
            ground_truth_path,
            probes_path,
            thresholds,
            skip_tier2,
            config_path,
            handover_path,
            output_dir,
        )


def _score(
    responses_path: str,
    ground_truth_path: str,
    probes_path: Optional[str],
    thresholds: Optional[ThresholdsConfig],
    skip_tier2: bool,
    config_path: Optional[str] = None,
    handover_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> dict[str, Any]:
    started = now_utc()

    # The pre-commitment gate, first, because it decides whether this run is entitled
    # to produce a report at all (§3.6). Everything below it is scoring; this is about
    # whether the answer key is the one that was sealed before the responses existed.
    if handover_path:
        handover = load_handover(handover_path)
        pre_commitment = verify_pre_commitment(
            handover, handover_path, ground_truth_path, probes_path
        )
    else:
        handover = None
        pre_commitment = PreCommitment(status="absent")

    # Checked once, before anything is read, rather than discovered part-way through a
    # run. A missing scoring dependency is our misconfiguration, not a property of the
    # target — a report that silently dropped two checks because of it would attribute
    # our setup to their system (NF9).
    tier2 = [spec for spec in REGISTRY if spec.tier == 2]
    available, why = tier2_available()
    if tier2 and not skip_tier2 and not available:
        raise ScoringError(
            f"The Tier 2 scoring layer is not installed, and "
            f"{len(tier2)} registered checks need it: "
            f"{', '.join(s.name for s in tier2)}.\n"
            f"    pip install --require-hashes -r requirements/score.txt\n"
            f"  Or pass --skip-tier2 to score the Tier 1 checks only; the report then\n"
            f"  records the Tier 2 checks as not run rather than omitting them.\n"
            f"  Original error: {why}"
        )

    response_file = load_responses(responses_path)
    ground_truth = load_ground_truth(ground_truth_path)
    thresholds = thresholds or ThresholdsConfig()

    if probes_path:
        probes = load_probes(probes_path)
        eligibility_source = "probe file"
    else:
        probes = _probes_from(response_file, ground_truth)
        eligibility_source = "ground-truth manifest (no probe file supplied)"

    answered = {r.probe_id for r in response_file.responses}
    declared = {p.probe_id for p in probes}
    if missing := declared - answered:
        logger.warning(
            f"{len(missing)} declared probes have no record in the response file: "
            f"{sorted(missing)}. They count as not captured, not as passes."
        )
    if extra := answered - declared:
        raise ScoringError(
            f"{responses_path}: records for probes that are not in the probe file: "
            f"{sorted(extra)}.\n"
            f"  Scoring a probe whose eligibility was never declared would put a\n"
            f"  result into a denominator that was fixed before the run (F39)."
        )

    checks = [
        score_check(
            spec,
            probes,
            response_file,
            ground_truth,
            thresholds,
            skipped=skip_tier2 and spec.tier == 2,
        )
        for spec in REGISTRY
    ]

    passes = max((r.pass_index for r in response_file.responses), default=1)

    # F41. Collected before the manifest so the evidence index is part of what the
    # findings digest covers — the excerpts are evidence, not decoration on top of it.
    by_probe_id = {p.probe_id: p for p in probes}
    grouped_responses = _by_probe(response_file.responses)
    instances = {
        c["check"]: evidence.collect(
            c["check"],
            c["tier"],
            c.get("detail", {}),
            by_probe_id,
            grouped_responses,
        )
        for c in checks
        if c["status"] == FAIL
    }
    instances = {check: rows for check, rows in instances.items() if rows}

    # The findings, and nothing else — in exactly the form they appear in the file, so
    # the digest below is one a reader can recompute from the document they hold.
    # NF2's byte-identical claim is about these and cannot be about a block that
    # records when the run happened.
    findings = build_findings(
        tier1=[c["check"] for c in checks if c["tier"] == 1],
        tier2=[c["check"] for c in checks if c["tier"] == 2],
        checks={c["check"]: c for c in checks},
        summary=_summarise(checks),
        capture={
            "eligibility_source": eligibility_source,
            "citations_captured": response_file.citations_captured(),
            "retrieved_chunks_captured": response_file.retrieved_chunks_captured(),
            "document_ids_supplied": bool(
                response_file.capture_notes
                and response_file.capture_notes.document_ids
            ),
            "passes": passes,
            "records": len(response_file.responses),
            "transport_errors": sum(
                1 for r in response_file.responses if not r.usable
            ),
        },
        evidence={
            check: {"file": f"evidence/{check}.md", "instances": len(rows)}
            for check, rows in instances.items()
        },
    )

    manifest = build_run_manifest(
        findings=findings,
        checks=checks,
        probes=probes,
        response_file=response_file,
        responses_path=responses_path,
        ground_truth_path=ground_truth_path,
        probes_path=probes_path,
        config_path=config_path,
        thresholds=thresholds,
        eligibility_source=eligibility_source,
        passes=passes,
        started=started,
        finished=now_utc(),
        skip_tier2=skip_tier2,
        pre_commitment=pre_commitment,
        handover=handover,
    )

    # Manifest first: a reader meets the provenance before the findings, which is the
    # order the argument has to be made in (§10.1).
    report = Report(manifest=manifest, **findings).to_document()

    if output_dir:
        write_bundle(output_dir, report, ground_truth_path, instances, probes)

    return report


def findings_of(report: dict[str, Any]) -> dict[str, Any]:
    """The report without its manifest — what NF2's determinism claim covers.

    Two runs over the same inputs produce identical findings and different manifests.
    Both halves of that are correct, and a determinism test that could not tell them
    apart would be testing the clock.
    """
    return {k: v for k, v in report.items() if k not in ("manifest", "schema")}


def _probes_from(response_file: ResponseFile, ground_truth: GroundTruth) -> list[Probe]:
    """Reconstruct eligibility when no probe file was supplied.

    Weaker than the real thing: it derives eligibility from which expectations exist,
    which is a statement about the ground truth rather than a commitment made before
    the run. Usable for a local re-score of a file we produced; not a substitute for
    the probe file in a report handed to a third party.
    """
    eligible: dict[str, list[str]] = defaultdict(list)
    for expectation in ground_truth.expectations:
        eligible[expectation.probe_id].append(expectation.check)

    probes = []
    for response in response_file.responses:
        if response.pass_index != 1:
            continue
        checks = eligible.get(response.probe_id)
        if not checks:
            continue
        probes.append(
            Probe(
                probe_id=response.probe_id,
                family=checks[0],
                intent="positive",
                text=response.query,
                tenant=response.tenant,
                eligible_for=checks,
            )
        )
    return probes


def _summarise(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts, never a rate (§3.5).

    A single headline percentage is what the register in Appendix D exists to prevent:
    it needs a denominator the reader cannot see, and it invites being quoted without
    one.
    """
    by_status: dict[str, int] = defaultdict(int)
    for check in checks:
        by_status[check["status"]] += 1

    tier1_failed = [
        c["check"] for c in checks if c["tier"] == 1 and c["status"] == FAIL
    ]
    tier2_failed = [
        c["check"] for c in checks if c["tier"] == 2 and c["status"] == FAIL
    ]

    return {
        "checks_registered": len(checks),
        "passed": by_status[PASS],
        "failed": by_status[FAIL],
        "not_eligible": by_status[NOT_ELIGIBLE],
        "not_captured": by_status[NOT_CAPTURED],
        # How much of the battery was published in advance (§3.6.1). Stated so the
        # withholding is a bounded, countable fact rather than an atmosphere.
        "published_keys": sum(1 for c in checks if c["key"] == "open"),
        "withheld_keys": sum(1 for c in checks if c["key"] == "held"),
        "tier1_findings": tier1_failed,
        "tier2_findings": tier2_failed,
        "verdict": FAIL if (tier1_failed or tier2_failed) else PASS,
    }
