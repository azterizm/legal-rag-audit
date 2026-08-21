"""Command line surface (V2_FULL_PLAN.md §7).

Five modes, and which side of the engagement runs each one is the whole design:

    legal-rag-audit plant  --mode existing -o run/     # §9.1's other configuration
    legal-rag-audit ingest --strict                    # re-check the anchors
    legal-rag-audit plant  --seed <seed> -o run/
    legal-rag-audit hash   --corpus run/corpus --probes run/probes.jsonl \
                           --ground-truth run/ground_truth.json -o run/handover.json
    legal-rag-audit validate -c config.yaml
    legal-rag-audit generate -c config.yaml --corpus run/corpus \
                             --probes-in run/probes.jsonl -o responses.jsonl
    legal-rag-audit score --responses responses.jsonl \
                          --ground-truth run/ground_truth.json \
                          --handover run/handover.json -o out/
    legal-rag-audit schema --print responses.v3

`plant` and `hash` run first and are ours: one mints the invariants and writes the corpus,
the other seals it before any response exists. `validate` and `generate` are theirs, and
`generate` is optional — they may replace it with their own harness and hand back a
conforming file. `score` is ours and runs offline. `schema` prints the published contract
so nobody has to clone anything to implement against it (F35).

`plant` is a mode §7 does not list. The plan's three-mode split is about *who runs what*,
and planting sits on our side alongside `hash` rather than adding a fourth party to the
engagement. It exists as a command for the same reason `hash` does: a pipeline step that
only ever ran inside another command could not be inspected, repeated, or checked by the
client.

`plant --mode existing` writes **no corpus**: §9.1's second configuration probes the
target's own index, so its ground truth is public rather than planted and it needs no
`upload` endpoint at all (F25). It shares the command rather than taking one of its own
because the operator is doing the same act — producing the two halves of a battery and
sealing them — and only the source of the answers differs.

`ingest` is the refresh procedure for that battery and is the only command that fetches
from a third party. It scores nothing and changes no ground truth: it re-checks that each
anchored phrase is still in the provision it was quoted from, so an anchor that has gone
stale is a reported event rather than a battery quietly scoring against a version of the
law that no longer exists.

Exit codes are a contract, because this runs in CI:

    0  ran, no findings
    1  ran, findings
    2  did not run — a setup problem, diagnosed (NF9)

Separating 2 from the other two is the point. A run that could not start must not exit
the way a clean run does, and must not exit the way a run with findings does either.

`validate` never returns 1. It makes no judgement about any answer, so it has no
findings; a setup check and an audit result sharing an exit code would be the same
conflation the mode exists to prevent.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .authorisation import PRODUCTION_ACK, AuthorisationError
from .config import AuditConfig
from .corpus_loader import CorpusError
from .interchange import InterchangeError, SchemaVersionError

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_SETUP = 2


def _configure_logging(verbose: bool, to_file: bool = True) -> None:
    """Log to the file and the terminal — except under `validate`, which writes nothing.

    `to_file` exists for one command. §7.1's claim is *nothing written*, and a mode
    offered to strangers as a free pre-sale check should not leave a log file in the
    directory they ran it from. A qualified claim would have been the easier fix and the
    worse one: the sentence is short because the behaviour is.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    unwritable = ""
    if to_file:
        # A read-only working directory is a supported configuration, not an error:
        # §12.3's hardened invocation runs the container with `--read-only`, and the
        # first thing a target would otherwise see is a traceback out of logging's
        # internals — loud, but not a diagnosis, which is the half of NF9 that matters.
        #
        # So the log file is best-effort and its absence is announced. It is a
        # convenience; the evidence is the report and the run manifest. Announced
        # rather than dropped because a run with no log and a run whose log was
        # written must not print the same thing (F40).
        try:
            handlers.insert(0, logging.FileHandler(".legal_rag_audit.log", mode="a"))
        except OSError as e:
            unwritable = str(e)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )
    if unwritable:
        logging.warning(
            "no .legal_rag_audit.log was written — the working directory is not "
            "writable (%s). This run is otherwise unaffected: the log is a "
            "convenience and the evidence is the report and the manifest.",
            unwritable,
        )


def _abort(message: str) -> int:
    logging.error(message)
    return EXIT_SETUP


def cmd_generate(args: argparse.Namespace) -> int:
    from .generate import GenerationError, generate
    from .transport.client import AuthTokenMissing

    try:
        config = AuditConfig.load_from_yaml(args.config)
    except Exception as e:
        return _abort(f"Could not load {args.config}: {e}")

    # The flag wins when it is given; the config is the default. `--passes` defaults to
    # None rather than 1 so `--passes 1` against a config asking for 3 is an instruction
    # and not indistinguishable from silence.
    passes = args.passes if args.passes is not None else config.battery.passes

    try:
        generate(
            config=config,
            responses_path=args.output,
            probes_path=args.probes,
            passes=passes,
            skip_upload=args.skip_upload,
            corpus_dir=args.corpus,
            probes_in=args.probes_in,
            production_ack=args.production_ack,
            request_delay=args.delay,
        )
    except AuthorisationError as e:
        return _abort(f"Refusing to run, and nothing was sent:\n{e}")
    except CorpusError as e:
        return _abort(f"Corpus setup failed, aborting before any request was sent:\n{e}")
    except AuthTokenMissing as e:
        return _abort(str(e))
    except GenerationError as e:
        return _abort(f"Generation failed, no response file written:\n{e}")

    # generate makes no judgement about the answers, so it has no findings to report.
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    """Three neutral probes, the raw body, the extraction, the diagnoses. Exit 0 or 2."""
    from .transport.client import AuthTokenMissing
    from .validate import render, validate

    try:
        config = AuditConfig.load_from_yaml(args.config)
    except Exception as e:
        return _abort(f"Could not load {args.config}: {e}")

    count, source = args.probe_count, "given on the command line"
    if count is None and args.probes:
        try:
            with open(args.probes, encoding="utf-8") as handle:
                # The probe file, not the battery module. Counting lines in a file the
                # operator already holds tells us the size of this run without giving
                # this package an import path to `probes/` (§7.1).
                count = sum(1 for line in handle if line.strip())
            source = f"counted from {args.probes}"
        except OSError as e:
            return _abort(f"Could not read {args.probes}: {e}")
    elif count is None:
        source = None

    try:
        result = validate(
            config,
            timeout=args.timeout,
            passes=args.passes,
            probe_count=count,
            probe_count_source=source,
            skip_upload=args.skip_upload,
        )
    except AuthTokenMissing as e:
        return _abort(str(e))
    print(render(result))
    return EXIT_SETUP if result.blocked else EXIT_OK


def cmd_score(args: argparse.Namespace) -> int:
    from .interchange import unrecorded_gaps
    from .provenance import HashError, PreCommitmentError
    from .score import ScoringError, score
    from .score.offline import OfflineViolation
    from .score.registry import GroundTruthIncomplete

    try:
        report = score(
            responses_path=args.responses,
            ground_truth_path=args.ground_truth,
            probes_path=args.probes,
            skip_tier2=args.skip_tier2,
            config_path=args.config,
            handover_path=args.handover,
            output_dir=args.output,
        )
    except (InterchangeError, SchemaVersionError) as e:
        return _abort(f"Could not read the input files:\n{e}")
    except PreCommitmentError as e:
        return _abort(str(e))
    except GroundTruthIncomplete as e:
        return _abort(f"The ground-truth manifest is incomplete:\n{e}")
    except HashError as e:
        return _abort(f"Could not compute a provenance digest:\n{e}")
    except ScoringError as e:
        return _abort(f"Scoring could not run:\n{e}")
    except OfflineViolation as e:
        return _abort(str(e))

    # A gap here is a defect in the manifest, not in the run: a §6.5 field that is
    # neither populated nor explained reads as completeness on the page. Loud, and
    # not fatal — the findings are still sound and suppressing them would be worse.
    if gaps := unrecorded_gaps(report["manifest"]):
        logging.warning(
            f"Run manifest has unexplained gaps: {', '.join(gaps)}. "
            f"Every §6.5 field should be populated or listed in `not_recorded`."
        )

    _print_summary(report["summary"], report["capture"], report["manifest"])

    return EXIT_FINDINGS if report["summary"]["verdict"] == "FAIL" else EXIT_OK


def _print_summary(summary: dict, capture: dict, manifest: dict) -> None:
    """Counts against declared denominators. Never a single headline rate (§3.5)."""
    print()
    print(f"  checks registered   {summary['checks_registered']}")
    print(f"  passed              {summary['passed']}")
    print(f"  findings            {summary['failed']}")
    print(f"  not eligible        {summary['not_eligible']}")
    print(f"  not captured        {summary['not_captured']}")
    if summary["tier1_findings"]:
        print(f"  Tier 1 (measured)   {', '.join(summary['tier1_findings'])}")
    if summary["tier2_findings"]:
        print(f"  Tier 2 (instrument) {', '.join(summary['tier2_findings'])}")
    if capture["transport_errors"]:
        print(
            f"  transport errors    {capture['transport_errors']}/"
            f"{capture['records']} records carried no answer — NOT_CAPTURED, "
            f"not findings"
        )

    # §8.3. On the console as well as the page, because an operator who ran one pass
    # should learn here that reproducibility was not measured — not three screens into
    # a report they may hand on before reading.
    variance = summary.get("variance") or {}
    if variance:
        if variance.get("passes", 1) < 2:
            print(
                "  variance            1 pass — nothing compared; reproducibility "
                "NOT measured (not a pass)"
            )
        elif not variance.get("compared"):
            # Three zeros beside "3 passes" reads as a measurement that found nothing,
            # and it is the absence of a measurement (F40, on the console). It happens
            # for a real reason: `response_divergence` is cross-cutting, probes declare
            # it and ground truth does not, so a `score` run given no probe file cannot
            # find it eligible and compares nothing. Say that, and say the fix.
            print(
                "  variance            "
                f"{variance['passes']} passes, 0 compared — reproducibility NOT "
                "measured"
            )
            print(
                "                      fix: pass --probes (response_divergence is "
                "declared by the probes, not the answer key)"
            )
        else:
            print(
                f"  variance            {variance['passes']} passes: "
                f"{variance['identical']} identical, "
                f"{variance['invariant_stable']} stable in prose, "
                f"{variance['divergent']} divergent"
            )
    print()
    # The two lines that make the report checkable by someone who does not trust it.
    print(f"  findings digest     {manifest['scoring']['findings_hash']}")
    print(f"  ground truth        {manifest['inputs']['ground_truth_manifest_hash']}")
    if manifest["pre_commitment"]["status"] == "verified":
        print(
            f"  pre-commitment      verified against "
            f"{manifest['pre_commitment']['handover_record']} "
            f"(committed {manifest['pre_commitment']['created']})"
        )
    else:
        print("  pre-commitment      none supplied — this run claims none")
    print()


def cmd_plant(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .interchange import write_ground_truth, write_probes
    from .plants import PlantError, PlantingError, plant, write_corpus
    from .probes import build_ground_truth, build_probes, validate_battery

    from .corpora import CorpusSpecError
    from .corpora import load as load_library_corpus

    if getattr(args, "list_corpora", False):
        return _list_corpora()

    out = Path(args.output)

    if args.mode == "existing":
        return _plant_existing(out, args)

    try:
        validate_battery()
        corpus = plant(args.seed, load_library_corpus(args.library))
        written = write_corpus(out / "corpus", corpus)
        probes = build_probes(passes=args.passes, corpus=corpus)
        ground_truth = build_ground_truth(corpus)
    except CorpusSpecError as e:
        return _abort(f"The corpus could not be read:\n{e}")
    except (PlantError, PlantingError) as e:
        return _abort(f"The corpus could not be planted:\n{e}")

    write_probes(out / "probes.jsonl", probes)
    write_ground_truth(out / "ground_truth.json", ground_truth)

    guard = ground_truth.guard
    print()
    print(f"  corpus              {corpus.source.label}  "
          f"({corpus.source.domain}; as at {corpus.source.as_at})")
    print(f"  seed                {corpus.seed}  ({corpus.seed_source})")
    print(f"  plants              {len(corpus.plants)}")
    print(f"  regenerations       {guard.regenerations if guard else 0}")
    print(f"  documents           {out / 'corpus'}  "
          f"({written['base']} base, {written['revision']} revision)")
    print(f"  probes              {out / 'probes.jsonl'}  ({len(probes)})")
    print(f"  ground truth        {out / 'ground_truth.json'}  "
          f"({len(ground_truth.expectations)} expectations)")
    if corpus.is_demo():
        print("  WARN                published demo seed — regenerable by anyone, "
              "establishes nothing about a target. Use --seed for an engagement.")
    print()
    print(
        f"  next (seal before the target sees anything):\n"
        f"    legal-rag-audit hash --corpus {out / 'corpus'} "
        f"--probes {out / 'probes.jsonl'} \\\n"
        f"                         --ground-truth {out / 'ground_truth.json'} "
        f"-o {out / 'handover.json'}"
    )
    print()
    return EXIT_OK


def _list_corpora() -> int:
    """What this build ships, and what each one is for."""
    from .corpora import CorpusSpecError, available
    from .corpora import load as load_library_corpus

    print()
    for name in available():
        try:
            corpus = load_library_corpus(name)
        except CorpusSpecError as e:
            # Printed rather than raised: one broken corpus must not hide the others,
            # and the whole point of the listing is to find out which one is broken.
            print(f"  {name:<24}  DOES NOT LOAD — {str(e).splitlines()[0]}")
            continue
        print(f"  {name:<24}  v{corpus.version}  {corpus.domain}")
        print(f"  {'':<24}  as at {corpus.as_at}, {corpus.jurisdiction}")
        for trigger in corpus.staleness_triggers:
            print(f"  {'':<24}  stale if: {trigger.instrument}")
        print()
    print("  Pass one to `plant --corpus <name>`, or a path to a directory of your own.")
    print()
    return EXIT_OK


def _plant_existing(out, args: argparse.Namespace) -> int:
    """The existing-corpus battery: probes and an answer key, and no corpus (F25).

    Shares `plant` rather than taking a command of its own, because what the operator is
    doing is the same act — producing the two halves of a battery and sealing them. What
    differs is where the answers come from, and that is what `--mode` names.
    """
    from .external import (
        AnchorError,
        InstrumentError,
        build_external_ground_truth,
        build_external_probes,
        validate_anchors,
        validate_instruments,
    )
    from .interchange import write_ground_truth, write_probes

    try:
        validate_anchors()
        validate_instruments()
        probes = build_external_probes(passes=args.passes)
        ground_truth = build_external_ground_truth()
    except AnchorError as e:
        return _abort(f"The anchor set is not usable:\n{e}")
    except InstrumentError as e:
        return _abort(f"The fictional-instrument set is not usable:\n{e}")

    write_probes(out / "probes.jsonl", probes)
    write_ground_truth(out / "ground_truth.json", ground_truth)

    print()
    print("  mode                existing — no corpus, no upload endpoint needed")
    print(f"  probes              {out / 'probes.jsonl'}  ({len(probes)})")
    print(
        f"  ground truth        {out / 'ground_truth.json'}  "
        f"({len(ground_truth.expectations)} expectations)"
    )
    print("  source              external and public — legislation.gov.uk phrases, "
          "published identifiers, off-register instruments")
    print("  authorisation       not required — nothing planted; every probe is a "
          "question anyone could type")
    print()
    print("  ORDER               run before any planted upload — planting indexes "
          "one of these fictional instruments")
    print("  WARN                bundled anchors ship in the wheel and are public. An "
          "engagement authors its own.")
    print()
    print(
        f"  next (seal before the target sees anything):\n"
        f"    legal-rag-audit hash --probes {out / 'probes.jsonl'} \\\n"
        f"                         --ground-truth {out / 'ground_truth.json'} "
        f"-o {out / 'handover.json'}"
    )
    print()
    return EXIT_OK


def cmd_ingest(args: argparse.Namespace) -> int:
    """Re-check every anchor against the primary source. Scores nothing."""
    from .external import ANCHORS
    from .external.ingest import IngestError, ingest

    try:
        store = ingest(ANCHORS)
    except IngestError as e:
        return _abort(str(e))

    drift = store.drift(ANCHORS)
    footprint = store.footprint()

    print()
    print(f"  anchors             {len(ANCHORS)}")
    print(f"  snapshots           {footprint['snapshots']}")
    print(
        f"  footprint           {footprint['stored_bytes']} bytes kept of "
        f"{footprint['fetched_bytes']} fetched"
    )
    print()
    for snapshot in store.snapshots:
        mark = "ok  " if snapshot.invariant_present else "GONE"
        print(f"  {mark}  {snapshot.anchor_id} @ {snapshot.as_at or 'current'}  "
              f"{snapshot.invariant!r}")
    print()

    if args.output:
        store.save(args.output)
        print(f"  Store written to {args.output}")
        print()

    if drift:
        print(f"  DRIFT               {len(drift)} anchor(s) disagree with the "
              f"primary source:")
        for problem in drift:
            print(f"    {problem}")
        print()
        print("  Scoring against these would test a version of the law that is no "
              "longer there. Fix the anchor, not the answer.")
        print()
        return EXIT_SETUP if args.strict else EXIT_OK

    print("  drift               none")
    print()
    return EXIT_OK


def cmd_hash(args: argparse.Namespace) -> int:
    from .interchange import write_handover
    from .provenance import HashError, build_handover

    if not (args.corpus or args.probes or args.ground_truth):
        return _abort(
            "Nothing to hash. Pass at least one of --corpus, --probes, "
            "--ground-truth."
        )

    try:
        record = build_handover(
            corpus=args.corpus,
            probes=args.probes,
            ground_truth=args.ground_truth,
            note=args.note,
        )
    except HashError as e:
        return _abort(str(e))

    if args.output:
        write_handover(args.output, record)
        logging.info(f"Handover record written to {args.output}")

    print(json.dumps(record.to_document(), indent=2, ensure_ascii=False))
    return EXIT_OK


def cmd_split(args: argparse.Namespace) -> int:
    from .interchange import (
        InterchangeError,
        rehydrate_response_file,
        split_response_file,
        verify_round_trip,
    )

    if args.rehydrate:
        if not args.output:
            return _abort("--rehydrate needs -o/--output: the file to write.")
        try:
            digest = rehydrate_response_file(args.responses, args.output)
        except InterchangeError as e:
            return _abort(str(e))
        print(f"  rehydrated       {args.output}")
        print(f"  sha256           {digest}")
        print("\nCompare against `source_sha256` in raw/index.json.")
        return EXIT_OK

    if args.verify:
        try:
            ok, expected, actual = verify_round_trip(args.responses)
        except (InterchangeError, OSError, KeyError, ValueError) as e:
            return _abort(str(e))
        print(f"  expected  sha256:{expected}")
        print(f"  rebuilt   sha256:{actual}")
        print(f"\n  {'MATCH — the split pair reproduces the original capture.' if ok else 'MISMATCH — do not rely on this pair.'}")
        # A pair that no longer rehydrates is a corrupted artefact, not a finding about
        # a target — NF9's distinction, and the reason this is EXIT_SETUP and not 1.
        return EXIT_OK if ok else EXIT_SETUP

    if not args.output:
        return _abort("Nothing to write to. Pass -o/--output: a directory.")

    try:
        result = split_response_file(
            args.responses, args.output, lean_name=args.lean_name
        )
    except InterchangeError as e:
        return _abort(str(e))

    mb = 1024 * 1024
    print(f"  source           {args.responses}")
    print(f"    sha256         {result.source_sha256}")
    print(f"    size           {result.source_bytes / mb:.2f} MB")
    print(f"  lean file        {result.lean_path}")
    print(f"    size           {result.lean_bytes / mb:.3f} MB  ({result.shrink_factor:.0f}x smaller)")
    print(f"  raw sidecars     {result.raw_dir}  ({len(result.sidecars)} files)")
    print(f"  index            {result.index_path}")
    print("\n  round trip       VERIFIED before writing — rehydrates to the source bytes")

    if result.dict_raw_probes:
        print(
            f"\n  NOTE  {len(result.dict_raw_probes)} record(s) carried an object "
            f"`raw_response`, which is the\n"
            f"        one form `score` can read (entity_masking). Scoring the lean file "
            f"reports\n"
            f"        that check as not captured. Rehydrate first if you need it: "
            f"{', '.join(result.dict_raw_probes[:5])}"
        )
    return EXIT_OK


def cmd_triage(args: argparse.Namespace) -> int:
    from .score.triage import build_divergences, build_rows, render_worksheet

    try:
        rows = build_rows(args.responses, args.probes, args.report)
        divergences = build_divergences(args.report, rows)
    except (OSError, ValueError, KeyError) as e:
        return _abort(f"Could not build the worksheet: {e}")

    text = render_worksheet(
        rows, target=args.target or "unnamed target", divergences=divergences
    )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        need = sum(1 for r in rows if r.needs_reading)
        print(f"  worksheet        {args.output}")
        print(f"  observations     {len(rows)}")
        print(f"  need reading     {need}  (flagged + unjudged + uncaptured)")
        print("\n  Nothing here is a finding until a person signs the line.")
    else:
        print(text)
    return EXIT_OK


def cmd_resume(args: argparse.Namespace) -> int:
    from .interchange import outstanding, write_remaining_probes

    try:
        state = outstanding(args.probes, args.responses, args.passes)
    except InterchangeError as e:
        return _abort(str(e))

    total = len(state.gathered)
    done = sum(1 for pid in state.gathered if pid not in state.remaining)
    print(f"  target            {args.passes} pass(es) per probe")
    print(f"  probes complete   {done} of {total}")
    print(f"  still outstanding {len(state.remaining)}")

    if state.unknown:
        print(
            f"\n  NOTE  {len(state.unknown)} probe id(s) in the response files are not "
            f"in this probe file:\n        {', '.join(state.unknown[:6])}\n"
            f"        They were ignored. A response file from a different battery is "
            f"the usual cause."
        )

    if state.complete:
        print("\n  Nothing outstanding. Merge the segments:")
        print("    legal-rag-audit merge --responses <seg1> <seg2> ... -o responses.jsonl")
        return EXIT_OK

    try:
        written = write_remaining_probes(args.probes, args.output, state)
    except InterchangeError as e:
        return _abort(str(e))

    shortfalls = set(state.remaining.values())
    print(f"\n  remaining probes  {args.output}  ({written})")
    if len(shortfalls) == 1:
        only = shortfalls.pop()
        print(f"  shortfall         {only} pass(es), the same for every probe")
        print(f"  ask next account  --probes-in {args.output} --passes {only}")
    else:
        # `generate` asks every probe the same number of times, so a single --passes
        # over the whole remaining set would over-ask the probes that are nearly done.
        # Against a quota measured in single-figure questions that is wasted budget, so
        # the recommendation is one pass at a time with a recompute between.
        lo, hi = min(shortfalls), max(shortfalls)
        print(f"  shortfall         uneven — between {lo} and {hi} passes per probe")
        print(f"  ask next account  --probes-in {args.output} --passes 1")
        print(
            f"\n  One pass, not {hi}: `generate` asks every probe the same number of "
            f"times, so\n  --passes {hi} here would ask the nearly-finished probes "
            f"{hi - lo} time(s) too many. Against a\n  quota measured in single-figure "
            f"questions that is budget spent on nothing."
        )
    print(
        "\n  Re-run this command after each account and it recomputes; nothing already\n"
        "  answered is asked again."
    )
    return EXIT_OK


def cmd_merge(args: argparse.Namespace) -> int:
    from .interchange import merge_segments

    try:
        summary = merge_segments(args.responses, args.output, note=args.note)
    except InterchangeError as e:
        return _abort(str(e))

    print(f"  merged            {args.output}")
    print(f"  segments          {summary['segments']}")
    print(f"  probes            {summary['probes']}")
    print(f"  records           {summary['records']}  ({summary['answered']} answered)")
    print(f"  dropped           {summary['dropped_superseded']} superseded failure(s)")
    thin = [p for p, n in summary["passes_per_probe"].items() if n < 2]
    if thin:
        print(
            f"\n  NOTE  {len(thin)} probe(s) carry a single pass, so `response_divergence`\n"
            f"        cannot compare them and the report will say so."
        )
    print(
        "\n  The header records that this file was assembled and why that weakens the\n"
        "  reproducibility claim. Do not strip it."
    )
    return EXIT_OK


def cmd_schema(args: argparse.Namespace) -> int:
    from .interchange import available_schemas, read_schema_document

    if args.list:
        for version in available_schemas():
            print(version)
        return EXIT_OK

    if not args.print_version:
        return _abort("Nothing to do: pass --print <version> or --list.")

    try:
        document = read_schema_document(args.print_version)
    except SchemaVersionError as e:
        return _abort(str(e))

    print(json.dumps(document, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="legal-rag-audit",
        description="Retrieval integrity diagnostic for legal RAG systems.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    val = sub.add_parser(
        "validate",
        help="check the harness can read the target's API. Scores nothing, writes "
        "nothing",
        description=(
            "Sends three neutral throwaway queries — never a battery probe — and "
            "prints the raw response body beside what the configured JSONPaths "
            "extracted from it. Names auth rejection, rate limiting, a stream that "
            "never terminates, a failed websocket handshake, an upload that issues no "
            "identifier, and a projected run length, each with what it would have "
            "looked like in a report if nobody had caught it. Exits 0 or 2; never 1, "
            "because it judges no answer."
        ),
    )
    val.add_argument("-c", "--config", required=True, help="path to config.yaml")
    val.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help=(
            "seconds to wait per query before calling it a stall. Short on purpose: "
            "the value of this mode is that it comes back with a diagnosis"
        ),
    )
    val.add_argument(
        "--skip-upload",
        action="store_true",
        help=(
            "do not upload the neutral test document. Whether the upload endpoint "
            "issues document identifiers then goes unchecked, and the run says so"
        ),
    )
    val.add_argument(
        "--probes",
        default=None,
        help=(
            "a probe file, so the run-length projection uses this run's exact probe "
            "count rather than the battery size this build ships"
        ),
    )
    val.add_argument(
        "--probe-count",
        type=int,
        default=None,
        help="project against this many probes per pass",
    )
    val.add_argument(
        "--passes",
        type=int,
        default=None,
        help="project against this many passes. Defaults to battery.passes",
    )
    val.set_defaults(func=cmd_validate)

    gen = sub.add_parser(
        "generate",
        help="fire the battery at the target and write responses.jsonl",
        description=(
            "Asks the battery and records what came back. Scores nothing. You may "
            "replace this entirely with your own tooling — see docs/responses-schema.md."
        ),
    )
    gen.add_argument("-c", "--config", required=True, help="path to config.yaml")
    gen.add_argument(
        "-o", "--output", default="responses.jsonl", help="where to write the responses"
    )
    gen.add_argument(
        "--probes",
        default=None,
        help="also write the probe file here (the questions, without expectations)",
    )
    gen.add_argument(
        "--passes",
        type=int,
        default=None,
        help=(
            "ask each probe N times and report inter-pass divergence (§8.3). "
            "Overrides battery.passes in the config; defaults to that, or to 1"
        ),
    )
    gen.add_argument(
        "--skip-upload",
        action="store_true",
        help="do not upload the corpus; assume the target already holds it",
    )
    gen.add_argument(
        "--corpus",
        default=None,
        help=(
            "use an already-planted corpus directory (holding base/ and revision/) "
            "rather than planting one. Requires --probes-in"
        ),
    )
    gen.add_argument(
        "--probes-in",
        default=None,
        help="ask the questions in this probe file rather than building the battery",
    )
    gen.add_argument(
        PRODUCTION_ACK,
        action="store_true",
        dest="production_ack",
        help=(
            "required in addition to the config when `authorisation.environment` is "
            "`production`. There is no config-only path to a production run (§13 rule "
            "2): a config is copied between runs and a command line is typed for one"
        ),
    )
    gen.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help="wait this long between requests. Overrides `battery.request_delay_seconds`; "
        "defaults to that, or to 0. A public trial will usually rate-limit an unpaced "
        "battery, and a run that collects 429s has measured nothing while spending "
        "someone else's quota",
    )
    gen.set_defaults(func=cmd_generate)

    pl = sub.add_parser(
        "plant",
        help="mint the seeded invariants, write the corpus, probes and answer key",
        description=(
            "Runs before everything else and is ours. Mints one invariant per declared "
            "slot from the run seed, guards it against collision with the corpus and "
            "with every other plant, and writes the two corpus states, the probe file "
            "and the ground-truth manifest. Hash the result with `hash` before the "
            "target sees any of it (§3.6)."
        ),
    )
    pl.add_argument(
        "--seed",
        default=None,
        help=(
            "the run seed. Omitted uses the published demo seed, and the manifest "
            "records that it did — a battery anyone can regenerate is right for a "
            "demonstration and wrong for an engagement"
        ),
    )
    pl.add_argument(
        "--corpus",
        default=None,
        dest="library",
        help=(
            "which corpus from the library to plant into — a name that ships with this "
            "build, or a path to a directory of your own (§9.5). Omitted uses "
            "`bundled-demo`, which is a demonstration and says so on its own face. Run "
            "`plant --list-corpora` to see what is available"
        ),
    )
    pl.add_argument(
        "--list-corpora",
        action="store_true",
        help="print the corpora this build ships and exit",
    )
    pl.add_argument(
        "-o", "--output", default="./run", help="directory to write the run into"
    )
    pl.add_argument(
        "--passes",
        type=int,
        default=1,
        help="how many times each probe should be asked",
    )
    pl.add_argument(
        "--mode",
        choices=("planted", "existing"),
        default="planted",
        help=(
            "`planted` authors the corpus and mints its invariants. `existing` writes "
            "no corpus at all: the battery scores against the target's own index using "
            "public ground truth, and needs no upload endpoint (§9.1, F25)"
        ),
    )
    pl.set_defaults(func=cmd_plant)

    ing = sub.add_parser(
        "ingest",
        help="re-check the point-in-time anchors against legislation.gov.uk",
        description=(
            "The refresh procedure for existing-corpus mode. Fetches each anchored "
            "provision as it stood on its date and confirms the phrase the battery "
            "scores against is still there. Scores no answers and changes no ground "
            "truth: an anchor that has drifted is reported so a person can fix the "
            "anchor, because the alternative is a battery quietly scoring against a "
            "version of the law that no longer exists."
        ),
    )
    ing.add_argument(
        "-o",
        "--output",
        default=None,
        help="write the snapshot store here (it is corroboration, not a scoring input)",
    )
    ing.add_argument(
        "--strict",
        action="store_true",
        help="exit 2 if any anchor has drifted, for running this on a schedule",
    )
    ing.set_defaults(func=cmd_ingest)

    sc = sub.add_parser(
        "score",
        help="score a response file offline and write the report",
        description=(
            "Reads a response file and a ground-truth manifest. Opens no sockets: an "
            "attempt raises (§5.1, F18)."
        ),
    )
    sc.add_argument("--responses", required=True, help="path to responses.jsonl")
    sc.add_argument(
        "--ground-truth", required=True, help="path to the ground-truth manifest"
    )
    sc.add_argument(
        "--probes",
        default=None,
        help=(
            "path to the probe file. Denominators come from its eligible_for; without "
            "it they are reconstructed from the ground truth, which is weaker and the "
            "report says so"
        ),
    )
    sc.add_argument(
        "-o",
        "--output",
        default="reports",
        help=(
            "directory for report.json, manifest.json and the disclosed "
            "ground_truth.json"
        ),
    )
    sc.add_argument(
        "--handover",
        default=None,
        help=(
            "path to the handover record from `hash`. The digests published before "
            "the run are recomputed; a ground truth that has moved since aborts"
        ),
    )
    sc.add_argument(
        "-c",
        "--config",
        default=None,
        help="the config `generate` ran with, so its hash is recorded in the manifest",
    )
    sc.add_argument(
        "--skip-tier2",
        action="store_true",
        help=(
            "score the Tier 1 checks only. The Tier 2 checks are reported as not run, "
            "not omitted"
        ),
    )
    sc.set_defaults(func=cmd_score)

    hs = sub.add_parser(
        "hash",
        help="digest the corpus, probes and ground truth for handover",
        description=(
            "The pre-commitment record (§3.6, F38). Run this before the engagement "
            "and give the output to the client: it fixes the answer key while it is "
            "still sealed. `score --handover` recomputes the digests and refuses to "
            "score a ground truth that has moved since."
        ),
    )
    hs.add_argument("--corpus", default=None, help="the corpus directory as handed over")
    hs.add_argument("--probes", default=None, help="path to probes.jsonl")
    hs.add_argument("--ground-truth", default=None, help="path to ground_truth.json")
    hs.add_argument(
        "-o", "--output", default=None, help="write the record here as well as stdout"
    )
    hs.add_argument(
        "--note", default=None, help="free text: who received this, and when"
    )
    hs.set_defaults(func=cmd_hash)

    sp = sub.add_parser(
        "split",
        help="move raw_response out of a response file into one file per observation",
        description=(
            "A response file carries the records a person reads and the target's own "
            "wire capture, and the second one ruins the first: one streamed probe can "
            "be 2.5 MB of frames around a 2 KB answer, and a fifteen-record file no "
            "editor will open is a file people take on trust. This moves "
            "`raw_response` to raw/<probe_id>.pass<N>.json, one file per observation, "
            "and nulls it in the record. The split is proven to rehydrate to the "
            "source bytes before anything is written, and `--verify` re-proves it "
            "afterwards. Scores nothing; the original is left untouched."
        ),
    )
    sp.add_argument("--responses", required=True, help="path to the response file")
    sp.add_argument(
        "-o", "--output", default=None, help="directory to write the split pair into"
    )
    sp.add_argument(
        "--lean-name",
        default="responses.jsonl",
        help="name of the lean response file (default: responses.jsonl)",
    )
    sp.add_argument(
        "--rehydrate",
        action="store_true",
        help="reverse: read a lean file plus its raw/ directory and write the "
        "monolithic file to --output",
    )
    sp.add_argument(
        "--verify",
        action="store_true",
        help="rehydrate a lean file in memory and check it still reproduces the "
        "digest recorded at split time. Writes nothing",
    )
    sp.set_defaults(func=cmd_split)

    tr = sub.add_parser(
        "triage",
        help="lay every observation beside its answer text for hand-verification",
        description=(
            "Decides nothing. `score` says what the evidence supports; this prints "
            "each observation next to the answer that produced it so a person can "
            "sign it off before anything is published. A FAIL on `abstention` means "
            "the answer contained a claim of the shape asked for — not that it "
            "attributed the claim to the instrument that does not exist, and only "
            "the second is a fabrication. Flagged rows are printed with the sentence "
            "the match sits in, because that distinction is a reading task."
        ),
    )
    tr.add_argument("--responses", required=True, help="path to responses.jsonl")
    tr.add_argument("--probes", required=True, help="path to probes.jsonl")
    tr.add_argument("--report", required=True, help="path to report.json from `score`")
    tr.add_argument("--target", default=None, help="label for the worksheet heading")
    tr.add_argument("-o", "--output", default=None, help="write the worksheet here")
    tr.set_defaults(func=cmd_triage)

    rs = sub.add_parser(
        "resume",
        help="work out which probes a further account still has to answer",
        description=(
            "A free trial answers a handful of questions and then returns 402, so no "
            "single account carries a 22-probe three-pass battery. This counts the "
            "passes that came back *with an answer* and writes a probe file holding "
            "only the shortfall. A record carrying a transport error is not an answer, "
            "so the probe it names is still outstanding — which is exactly why the "
            "first exhausted account's 402s have to be re-asked rather than merged in."
        ),
    )
    rs.add_argument("--probes", required=True, help="the full sealed probe file")
    rs.add_argument(
        "--responses", nargs="+", required=True, help="every segment gathered so far"
    )
    rs.add_argument(
        "--passes", type=int, default=3, help="passes wanted per probe (default 3)"
    )
    rs.add_argument(
        "-o", "--output", default=None, help="write the remaining probe file here"
    )
    rs.set_defaults(func=cmd_resume)

    mg = sub.add_parser(
        "merge",
        help="join response segments from several accounts into one file",
        description=(
            "Drops error records a later segment answered, keeps every surviving "
            "record verbatim, and renumbers `pass_index` so the file satisfies "
            "one-record-per-(probe_id, pass_index). The header records that the file "
            "was assembled and that passes drawn from different accounts measure "
            "account-to-account variation as well as reproducibility — those are "
            "different claims and only the weaker one is supported."
        ),
    )
    mg.add_argument(
        "--responses", nargs="+", required=True, help="segments, in precedence order"
    )
    mg.add_argument("-o", "--output", required=True, help="where to write the merged file")
    mg.add_argument("--note", default=None, help="free text appended to the header note")
    mg.set_defaults(func=cmd_merge)

    schema = sub.add_parser(
        "schema",
        help="print a published JSON Schema",
        description="The interchange contracts, so you can implement against them.",
    )
    schema.add_argument(
        "--print", dest="print_version", metavar="VERSION", help="e.g. responses.v1"
    )
    schema.add_argument(
        "--list", action="store_true", help="list the versions this build publishes"
    )
    schema.set_defaults(func=cmd_schema)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose, to_file=args.command != "validate")
    try:
        sys.exit(args.func(args))
    except OSError as e:
        # A path that cannot be read or written is a setup problem, and NF9 says a
        # setup problem aborts with a diagnosis rather than a traceback. This became
        # visible with the container: §12.3's invocation runs `--read-only`, so a
        # forgotten `-v` mount lands here, and what a target saw was fifteen frames of
        # pathlib. `filename` is the whole diagnosis — it names the path that is wrong.
        #
        # Deliberately at the top rather than per command: every command that writes
        # has the same failure and would otherwise need the same handler, and one that
        # was forgotten would be the one a stranger hit.
        # `filename` is also what makes this safe to catch broadly. A socket error is
        # an OSError too, and calling a refused connection "a path problem" would be
        # a worse diagnosis than the traceback it replaced. No filename, no rewrite.
        if not e.filename:
            raise
        sys.exit(
            _abort(
                f"{e.strerror or e} — {e.filename}\n\n"
                "This is a path problem, not a finding. Nothing was scored. Check the "
                "directory exists and is writable by the user running this — in a "
                "container, that it is mounted (docs/hardened-run.md)."
            )
        )


if __name__ == "__main__":
    main()
