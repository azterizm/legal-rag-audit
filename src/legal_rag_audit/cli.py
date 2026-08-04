"""Command line surface (V2_FULL_PLAN.md §7).

Five modes, and which side of the engagement runs each one is the whole design:

    legal-rag-audit plant  --seed <seed> -o run/
    legal-rag-audit hash   --corpus run/corpus --probes run/probes.jsonl \
                           --ground-truth run/ground_truth.json -o run/handover.json
    legal-rag-audit generate -c config.yaml --corpus run/corpus \
                             --probes-in run/probes.jsonl -o responses.jsonl
    legal-rag-audit score --responses responses.jsonl \
                          --ground-truth run/ground_truth.json \
                          --handover run/handover.json -o out/
    legal-rag-audit schema --print responses.v2

`plant` and `hash` run first and are ours: one mints the invariants and writes the corpus,
the other seals it before any response exists. `generate` is theirs and optional — they
may replace it with their own harness and hand back a conforming file. `score` is ours and
runs offline. `schema` prints the published contract so nobody has to clone anything to
implement against it (F35).

`plant` is a fifth mode §7 does not list. The plan's three-mode split is about *who runs
what*, and planting sits on our side alongside `hash` rather than adding a fourth party to
the engagement. It exists as a command for the same reason `hash` does: a pipeline step
that only ever ran inside another command could not be inspected, repeated, or checked by
the client.

`validate` is Phase F and is not here yet.

Exit codes are a contract, because this runs in CI:

    0  ran, no findings
    1  ran, findings
    2  did not run — a setup problem, diagnosed (NF9)

Separating 2 from the other two is the point. A run that could not start must not exit
the way a clean run does, and must not exit the way a run with findings does either.
"""

import argparse
import json
import logging
import sys

from .config import AuditConfig
from .corpus_loader import CorpusError
from .interchange import InterchangeError, SchemaVersionError

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_SETUP = 2


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(".legal_rag_audit.log", mode="a"),
            logging.StreamHandler(),
        ],
    )


def _abort(message: str) -> int:
    logging.error(message)
    return EXIT_SETUP


def cmd_generate(args: argparse.Namespace) -> int:
    from .generate import GenerationError, generate

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
        )
    except CorpusError as e:
        return _abort(f"Corpus setup failed, aborting before any request was sent:\n{e}")
    except GenerationError as e:
        return _abort(f"Generation failed, no response file written:\n{e}")

    # generate makes no judgement about the answers, so it has no findings to report.
    return EXIT_OK


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
            f"  transport errors    {capture['transport_errors']} of "
            f"{capture['records']} records carried no answer — not captured, "
            f"not findings"
        )

    # §8.3. On the console as well as the page, because an operator who ran one pass
    # should learn here that reproducibility was not measured — not three screens into
    # a report they may hand on before reading.
    variance = summary.get("variance") or {}
    if variance:
        if variance.get("passes", 1) < 2:
            print(
                "  variance            one pass — nothing compared. Reproducibility "
                "was not measured, and this is not a pass"
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

    out = Path(args.output)
    try:
        validate_battery()
        corpus = plant(args.seed)
        written = write_corpus(out / "corpus", corpus)
        probes = build_probes(passes=args.passes, corpus=corpus)
        ground_truth = build_ground_truth(corpus)
    except (PlantError, PlantingError) as e:
        return _abort(f"The corpus could not be planted:\n{e}")

    write_probes(out / "probes.jsonl", probes)
    write_ground_truth(out / "ground_truth.json", ground_truth)

    guard = ground_truth.guard
    print()
    print(f"  seed                {corpus.seed}  ({corpus.seed_source})")
    print(f"  plants              {len(corpus.plants)}")
    print(f"  regenerations       {guard.regenerations if guard else 0}")
    print(f"  corpus              {out / 'corpus'}  "
          f"({written['base']} base, {written['revision']} revision)")
    print(f"  probes              {out / 'probes.jsonl'}  ({len(probes)})")
    print(f"  ground truth        {out / 'ground_truth.json'}  "
          f"({len(ground_truth.expectations)} expectations)")
    print()
    if corpus.is_demo():
        print(
            "  This is the published demo seed. Anyone can regenerate this corpus and "
            "this\n  answer key, so a report from it demonstrates the method and "
            "establishes nothing\n  about a target. Pass --seed for an engagement."
        )
        print()
    print(
        f"  Next: seal it before the target sees anything.\n"
        f"    legal-rag-audit hash --corpus {out / 'corpus'} "
        f"--probes {out / 'probes.jsonl'} \\\n"
        f"                         --ground-truth {out / 'ground_truth.json'} "
        f"-o {out / 'handover.json'}"
    )
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
        "-o", "--output", default="./run", help="directory to write the run into"
    )
    pl.add_argument(
        "--passes",
        type=int,
        default=1,
        help="how many times each probe should be asked",
    )
    pl.set_defaults(func=cmd_plant)

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
    _configure_logging(args.verbose)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
