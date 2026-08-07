"""Building the two provenance records: the handover, and the run manifest.

`build_handover` runs before the engagement and knows nothing about results.
`build_run_manifest` runs after scoring and knows nothing about the corpus. That
asymmetry is not an oversight — `score` never sees the corpus (§5.1), so a corpus
digest in the report can only be one that was committed to earlier, and it is
labelled as carried rather than computed.

`verify_pre_commitment` is the join between them, and the only reason the handover
record is more than a number in a covering email.
"""

from pathlib import Path
from typing import Any, Optional

from ..authorisation import reasons
from ..config import ThresholdsConfig
from ..instruments import describe
from ..interchange import (
    BatteryComposition,
    CaptureSummary,
    GroundTruth,
    Handover,
    HashedArtefact,
    InputDigests,
    InstrumentRecord,
    PreCommitment,
    Probe,
    ResponseFile,
    RunFacts,
    RunManifest,
    ScoringFacts,
    ToolProvenance,
    now_utc,
)
from .hashes import JSON_RECIPE, hash_file, hash_json, hash_path, recipe_for
from .tool import tool_provenance


class PreCommitmentError(Exception):
    """An artefact does not match what was committed to at handover.

    A setup problem in the loudest sense (NF9). It aborts: a report scored against a
    key that changed after the responses came back is the exact artefact §3.6 exists
    to make impossible, and producing one with a warning attached would be worse than
    producing none.
    """


def _artefact(label: str, path: str | Path) -> HashedArtefact:
    digest, kind, files = hash_path(path)
    return HashedArtefact(
        # The name, never the path — defect 22 one file over. `handover.json` is
        # published before the run and travels with the bundle, and an absolute path
        # inside it names a directory on the operator's machine. Working directories get
        # named after clients: the first two runs of this tool were fired from
        # directories called after the product under test, and this field wrote that name
        # into the sealed record of a run whose every other artefact was anonymous.
        #
        # Nothing is lost. `verify_pre_commitment` takes the paths it checks from the
        # command line, never from here, and the digest beside this field is what
        # identifies the artefact. The path only ever identified the laptop.
        path=Path(path).name,
        kind=kind,
        digest=digest,
        files=files,
        recipe=recipe_for(kind),
    )


def build_handover(
    corpus: Optional[str] = None,
    probes: Optional[str] = None,
    ground_truth: Optional[str] = None,
    note: Optional[str] = None,
) -> Handover:
    """The pre-commitment record, computed before any response exists (F38)."""
    tool = tool_provenance()
    return Handover(
        created=now_utc(),
        tool_version=tool["version"],
        tool_commit_sha=tool["commit_sha"],
        corpus=_artefact("corpus", corpus) if corpus else None,
        probes=_artefact("probes", probes) if probes else None,
        ground_truth=_artefact("ground_truth", ground_truth) if ground_truth else None,
        note=note,
    )


def verify_pre_commitment(
    handover: Handover,
    handover_path: str,
    ground_truth_path: str,
    probes_path: Optional[str],
) -> PreCommitment:
    """Recompute what this run can, and refuse if anything moved.

    The corpus cannot be checked here and is carried through with that stated. The
    ground truth can, and it is the one that matters: it is the artefact whose
    late editing would turn a diagnostic into a fabrication.
    """
    verified: list[str] = []
    carried: list[str] = []
    mismatches: list[str] = []

    def check(label: str, artefact: Optional[HashedArtefact], path: Optional[str]):
        if artefact is None:
            return
        if path is None:
            carried.append(label)
            return
        actual = hash_file(path)
        if actual != artefact.digest:
            mismatches.append(
                f"    {label}: committed {artefact.digest}\n"
                f"    {' ' * len(label)}  supplied  {actual}  ({path})"
            )
        else:
            verified.append(label)

    check("ground_truth", handover.ground_truth, ground_truth_path)
    check("probes", handover.probes, probes_path)
    if handover.corpus is not None:
        carried.append("corpus")

    if mismatches:
        raise PreCommitmentError(
            f"The artefacts do not match the handover record at {handover_path}, "
            f"committed {handover.created}:\n"
            + "\n".join(mismatches)
            + "\n\n"
            "  Refusing to score. A report produced from an answer key that changed\n"
            "  after the responses came back cannot be told apart from one that did\n"
            "  not, which is the whole reason the digest was published first (§3.6).\n"
            "  Either supply the artefacts as handed over, or score without\n"
            "  --handover and accept that the run makes no pre-commitment claim."
        )

    return PreCommitment(
        status="verified",
        # The file's name, never the path to it. An absolute path is worthless to a
        # reader — it names a directory on somebody else's laptop — and it carries
        # whatever the operator called that directory. Working directories get named
        # after clients, and this field put one in the report of a run whose every other
        # artefact was anonymous (defect 22). The digests below are what identify the
        # record; the path only ever identified the machine.
        handover_record=Path(handover_path).name,
        created=handover.created,
        verified=sorted(verified),
        carried=sorted(carried),
    )


def _battery(probes: list[Probe]) -> BatteryComposition:
    eligible: dict[str, int] = {}
    for probe in probes:
        for check in probe.eligible_for:
            eligible[check] = eligible.get(check, 0) + 1
    return BatteryComposition(
        total_probes=len(probes),
        positive_probes=sum(1 for p in probes if p.intent == "positive"),
        no_correct_answer_probes=sum(
            1 for p in probes if p.intent == "no_correct_answer"
        ),
        eligible_by_check=dict(sorted(eligible.items())),
    )


def _capture(
    response_file: ResponseFile,
    checks: list[dict[str, Any]],
    asked: Optional[dict[str, Any]] = None,
) -> CaptureSummary:
    notes = response_file.capture_notes
    return CaptureSummary(
        records=len(response_file.responses),
        transport_errors=sum(1 for r in response_file.responses if not r.usable),
        citations_captured=bool(response_file.citations_captured()),
        retrieved_chunks_captured=bool(response_file.retrieved_chunks_captured()),
        document_ids_supplied=bool(notes and notes.document_ids),
        probes_asked_verbatim=(asked or {}).get("asked_verbatim", 0),
        probes_asked_wrapped=list((asked or {}).get("asked_wrapped", [])),
        # Every check that produced no verdict, with the reason it gives. This is the
        # §6.5 line "what the response file did not carry, and which checks that
        # disabled", assembled from the checks themselves rather than restated — so
        # it cannot disagree with the body of the report.
        checks_not_run={
            c["check"]: c.get("reason", "no reason recorded")
            for c in checks
            if c["status"] in ("NOT_CAPTURED", "NOT_ELIGIBLE")
        },
        notes=notes.notes if notes else None,
    )


def build_run_manifest(
    *,
    findings: dict[str, Any],
    checks: list[dict[str, Any]],
    probes: list[Probe],
    response_file: ResponseFile,
    responses_path: str,
    ground_truth_path: str,
    probes_path: Optional[str],
    config_path: Optional[str],
    thresholds: ThresholdsConfig,
    eligibility_source: str,
    passes: int,
    started: str,
    finished: str,
    skip_tier2: bool,
    pre_commitment: PreCommitment,
    handover: Optional[Handover] = None,
    ground_truth: Optional[GroundTruth] = None,
    asked: Optional[dict[str, Any]] = None,
) -> RunManifest:
    """Assemble the §6.5 record for one scoring run."""
    not_recorded: dict[str, str] = {}

    corpus_hash = None
    corpus_provenance = None
    if handover and handover.corpus:
        corpus_hash = handover.corpus.digest
        corpus_provenance = (
            f"carried from the handover record committed {handover.created}. "
            f"`score` does not read the corpus and did not recompute this."
        )
    else:
        not_recorded["inputs.corpus_hash"] = (
            "no handover record was supplied. `score` never reads the corpus (§5.1), "
            "so the only way a corpus digest can appear in a report is to have been "
            "committed to before the run — run `legal-rag-audit hash --corpus …` at "
            "handover and pass the record with --handover."
        )

    config_hash = hash_file(config_path) if config_path else None
    if config_hash is None:
        not_recorded["inputs.config_hash"] = (
            "no config was supplied to `score`. The config governs `generate`, which "
            "ran elsewhere; pass --config to record the one used."
        )

    query_set_hash = hash_file(probes_path) if probes_path else None
    if query_set_hash is None:
        not_recorded["inputs.query_set_hash"] = (
            "no probe file was supplied, so eligibility was reconstructed from the "
            "ground truth (F39) and there is no query set to digest."
        )

    tool = tool_provenance()
    if tool["commit_sha"] is None:
        not_recorded["tool.commit_sha"] = tool["commit_unavailable"]

    # Both come off the ground-truth manifest, which is the one artefact `score` reads
    # that knows how the corpus was made. A run whose plants were minted from the
    # published demo seed has to say so on the page: those invariants are regenerable by
    # anyone, so nothing about the run turns on their being unguessable.
    seed = ground_truth.seed if ground_truth else None
    if seed is None:
        not_recorded["run.seed"] = (
            "the ground-truth manifest carries no seed, so this battery was not planted "
            "from one. Its expectations were authored directly, and a report from it "
            "cannot claim its invariants were unguessable."
        )

    # Declared by whatever built the answer key, not inferred here. `score` sees no
    # config and no corpus, and the absence of plants is true of a hand-authored planted
    # battery as well as of an existing-corpus one — so inferring it would mean the
    # report naming §9.1's configuration on a guess.
    corpus_mode = ground_truth.corpus_mode if ground_truth else None
    if corpus_mode is None:
        not_recorded["run.corpus_mode"] = (
            "the ground-truth manifest does not declare which of the two configurations "
            "in §9.1 this battery is for, and `score` sees no config and no corpus to "
            "tell from. A finding against documents we authored and a finding against "
            "the target's own index answer different objections, so this is left unsaid "
            "rather than guessed."
        )

    # Named by whatever built the answer key, for the same reason `corpus_mode` is: the
    # seed alone does not identify a battery, because the same seed against two corpora
    # mints the same values into different documents and asks different questions.
    corpus_ref = ground_truth.corpus if ground_truth else None
    if corpus_ref is None and corpus_mode != "existing":
        not_recorded["run.corpus"] = (
            "the ground-truth manifest does not name a corpus from the library. Two "
            "reports from the same seed and different corpora are not comparable, and "
            "neither can be reproduced by anyone who does not already know which corpus "
            "was used."
        )

    instruments = [InstrumentRecord(**row) for row in describe(thresholds)]

    # §13 rule 3 — verbatim, from the response file rather than from a config. `score`
    # sees no config, and on the artefact route (§5.1.1) the config never exists on our
    # machine at all; the producer of the responses is the party who holds the consent.
    notes = response_file.capture_notes
    authorisation = notes.authorisation if notes else None
    if authorisation is None:
        needed = reasons(
            (p.family for p in probes),
            uploads=bool(notes and notes.document_ids),
        )
        if needed:
            # Recorded, not refused. The gate that stops an unauthorised run is in
            # `generate`, before the first request goes out; by the time a response file
            # exists the requests have been sent, and refusing to score it would not
            # un-send them — it would only mean nobody got a report about what happened.
            #
            # It also has to stay scoreable because of the artefact route (§5.1.1): a
            # response file produced by the target's own harness against their own system
            # legitimately carries no block, and that is the whole low-friction premise.
            #
            # So the report says so, on the page, under Limits. An absent record of
            # consent and a recorded one must never read the same (F40).
            not_recorded["authorisation"] = (
                "this battery contains families that need written authorisation under "
                "§13 ("
                + ", ".join(
                    r.what.replace("the `", "").replace("` family", "")
                    for r in needed
                    if r.what != "uploading a corpus"
                )
                + "), and the response file carries no record of consent. This report "
                "cannot say who authorised the run that produced it. A file from the "
                "target's own harness against their own system is the ordinary reason "
                "for this; a run of ours would have aborted before sending anything."
            )
        else:
            not_recorded["authorisation"] = (
                "no authorisation block, and none was needed: every family in this "
                "battery is ordinary use under §13 and nothing was uploaded. Asking "
                "questions and reading the answers is the use a trial exists for."
            )

    return RunManifest(
        tool=ToolProvenance(
            version=tool["version"],
            commit_sha=tool["commit_sha"],
            commit_signature=tool["commit_signature"],
            commit_signature_verify_with=tool["commit_signature_verify_with"],
            working_tree=tool["working_tree"],
            commit_unavailable=tool["commit_unavailable"],
        ),
        inputs=InputDigests(
            responses_hash=hash_file(responses_path),
            query_set_hash=query_set_hash,
            ground_truth_manifest_hash=hash_file(ground_truth_path),
            config_hash=config_hash,
            corpus_hash=corpus_hash,
            corpus_hash_provenance=corpus_provenance,
            recipes={
                "file": recipe_for("file"),
                "tree": recipe_for("tree"),
                "findings_hash": JSON_RECIPE,
            },
        ),
        pre_commitment=pre_commitment,
        run=RunFacts(
            started=started,
            finished=finished,
            passes=passes,
            seed=seed,
            seed_source=ground_truth.seed_source if ground_truth else None,
            corpus_mode=corpus_mode,
            corpus=corpus_ref.label if corpus_ref else None,
            corpus_digest=corpus_ref.digest if corpus_ref else None,
            staleness_triggers=[
                f"{t.instrument} — {t.invalidates}"
                + (f" (watch: {t.watch})" if t.watch else "")
                for t in (corpus_ref.staleness_triggers if corpus_ref else [])
            ],
            plants=len(ground_truth.plants) if ground_truth else 0,
            remote_scoring=False,
            eligibility_source=eligibility_source,
        ),
        scoring=ScoringFacts(
            checks_registered=len(checks),
            tier2_skipped=skip_tier2,
            instruments=instruments,
            findings_hash=hash_json(findings),
            findings_hash_recipe=JSON_RECIPE,
        ),
        battery=_battery(probes),
        capture=_capture(response_file, checks, asked),
        authorisation=authorisation.to_record() if authorisation else None,
        not_recorded=dict(sorted(not_recorded.items())),
    )
