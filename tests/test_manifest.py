"""Provenance: the hashes, the pre-commitment, and what the manifest refuses to omit.

Everything here defends one property — that a report can be handed to somebody who
does not trust us and still mean something. Three separable claims:

1. The digests are reproducible **without this software**. A hash only a tool can
   recompute is a hash nobody checks, so the published recipes are executed here with
   `shasum` and compared against what the tool produced.
2. The pre-commitment is a **precondition**, not an undertaking. A ground truth that
   moved after handover aborts the run rather than producing a report with a caveat.
3. The manifest **has no silent holes**. A §6.5 field this build cannot populate is
   present, null, and explained; the same rule F40 applies to checks.
"""

import json
import shutil
import subprocess

import pytest

from legal_rag_audit.instruments import (
    BY_CHECK,
    EMBEDDING_MODEL,
    ENTAILMENT_MODEL,
    INSTRUMENTS,
)
from legal_rag_audit.interchange import (
    Handover,
    Response,
    load_handover,
    unrecorded_gaps,
    write_ground_truth,
    write_handover,
    write_probes,
    write_responses,
)
from legal_rag_audit.probes import build_ground_truth, build_probes
from legal_rag_audit.provenance import (
    PreCommitmentError,
    build_handover,
    digest_bytes,
    hash_file,
    hash_json,
    hash_path,
    hash_tree,
)
from legal_rag_audit.provenance.hashes import HashError
from legal_rag_audit.score import score

HAS_SHASUM = shutil.which("shasum") is not None


def make_run(tmp_path):
    """A complete, scorable input set. Returns the three paths."""
    probes = build_probes()
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "ground_truth.json", build_ground_truth())
    write_responses(
        tmp_path / "responses.jsonl",
        [
            Response(
                run_id="r",
                probe_id=p.probe_id,
                query=p.text,
                tenant=p.tenant,
                answer="A generic answer with nothing in it.",
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


# ------------------------------------------------------- digests anyone can recompute


def test_a_file_digest_is_plain_sha256_of_the_bytes(tmp_path):
    """No framing, no canonicalisation, nothing to get wrong at the other end."""
    path = tmp_path / "artefact.json"
    path.write_bytes(b'{"a": 1}\n')
    assert hash_file(path) == digest_bytes(b'{"a": 1}\n')


@pytest.mark.skipif(not HAS_SHASUM, reason="shasum is not on this machine")
def test_the_published_file_recipe_is_the_one_the_tool_uses(tmp_path):
    path = tmp_path / "ground_truth.json"
    write_ground_truth(path, build_ground_truth())

    out = subprocess.run(
        ["shasum", "-a", "256", str(path)], capture_output=True, text=True, check=True
    )
    assert hash_file(path) == f"sha256:{out.stdout.split()[0]}"


@pytest.mark.skipif(not HAS_SHASUM, reason="shasum is not on this machine")
def test_the_published_tree_recipe_reproduces_the_corpus_digest(tmp_path):
    """The recipe in TREE_RECIPE, run as a shell pipeline, against the tool's answer.

    This is the test that matters most in this file. A directory has no bytes of its
    own, so a tree digest is entirely a matter of convention — which files, in which
    order, spelled how — and a convention only we can execute is not verifiable by a
    client. If this ever diverges, the recipe printed in the handover record is a
    false instruction, which is worse than printing none.
    """
    corpus = tmp_path / "corpus"
    (corpus / "nested").mkdir(parents=True)
    (corpus / "b.txt").write_text("second\n")
    (corpus / "a.txt").write_text("first\n")
    (corpus / "nested" / "c.md").write_text("third\n")

    recipe = (
        "find . -type f -not -path '*/.*' | sed 's|^\\./||' | LC_ALL=C sort "
        "| tr '\\n' '\\0' | xargs -0 shasum -a 256 | shasum -a 256"
    )
    out = subprocess.run(
        ["sh", "-c", recipe], cwd=corpus, capture_output=True, text=True, check=True
    )
    assert hash_tree(corpus).digest == f"sha256:{out.stdout.split()[0]}"


def test_a_tree_digest_ignores_filesystem_noise(tmp_path):
    """A .DS_Store must not read as a tampered corpus.

    The exclusion is a real decision with a real cost — it means a dot-file inside a
    corpus is outside the commitment — and it is stated in TREE_RECIPE for that
    reason. The cost is worth paying: a pre-commitment that fires on macOS Finder
    trains people to ignore it, and an ignored alarm protects nobody.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.txt").write_text("content\n")
    before = hash_tree(corpus).digest

    (corpus / ".DS_Store").write_bytes(b"\x00\x01noise")
    assert hash_tree(corpus).digest == before

    (corpus / "doc.txt").write_text("content, edited\n")
    assert hash_tree(corpus).digest != before


def test_a_tree_digest_is_independent_of_walk_order(tmp_path):
    """Sorted by path as bytes, so two machines agree."""
    one, two = tmp_path / "one", tmp_path / "two"
    for root, order in ((one, "abc"), (two, "cba")):
        root.mkdir()
        for name in order:
            (root / f"{name}.txt").write_text(f"{name}\n")
    assert hash_tree(one).digest == hash_tree(two).digest


def test_hashing_something_that_is_not_there_is_loud(tmp_path):
    with pytest.raises(HashError, match="no such file or directory"):
        hash_path(tmp_path / "absent")


def test_a_json_digest_is_a_property_of_the_data_not_the_formatting():
    assert hash_json({"a": 1, "b": [2, 3]}) == hash_json({"b": [2, 3], "a": 1})
    assert hash_json({"a": 1}) != hash_json({"a": 2})


# --------------------------------------------------------------- the handover record


def test_the_handover_record_carries_its_own_verification_instructions(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.txt").write_text("content\n")
    _, gt, probes = make_run(tmp_path)

    record = build_handover(corpus=str(corpus), probes=probes, ground_truth=gt)

    assert record.corpus.kind == "tree" and record.corpus.files == 1
    assert record.probes.kind == "file"
    for artefact in record.artefacts().values():
        assert artefact.digest.startswith("sha256:")
        assert "shasum -a 256" in artefact.recipe


def test_a_handover_record_round_trips_through_the_published_schema(tmp_path):
    _, gt, probes = make_run(tmp_path)
    written = tmp_path / "handover.json"
    write_handover(written, build_handover(probes=probes, ground_truth=gt))

    reloaded = load_handover(written)
    assert reloaded.ground_truth.digest == hash_file(gt)


def test_an_unknown_handover_version_is_refused_not_guessed(tmp_path):
    """NF10. A best-effort read of a record we do not understand produces a
    pre-commitment claim about a file we did not parse."""
    from legal_rag_audit.interchange import SchemaVersionError

    path = tmp_path / "handover.json"
    path.write_text(json.dumps({"schema": "handover.v9", "created": "x"}))
    with pytest.raises(SchemaVersionError, match="handover.v9"):
        load_handover(path)


# -------------------------------------------------- the pre-commitment is enforced


def test_a_ground_truth_that_moved_after_handover_aborts_the_run(tmp_path):
    """§3.6, and the reason the mechanism is worth having at all.

    The accusation it answers is not 'the vendor cheated' — it is 'you decided what
    counted as a failure after you saw the failure'. That one is otherwise
    unanswerable and voids every finding in the document. So: not a warning on the
    page, not a flag in the manifest. The run does not happen.
    """
    responses, gt, probes = make_run(tmp_path)
    handover = tmp_path / "handover.json"
    write_handover(handover, build_handover(probes=probes, ground_truth=gt))

    document = json.loads(open(gt, encoding="utf-8").read())
    document["expectations"][0]["must_not_contain"].append("decided afterwards")
    open(gt, "w", encoding="utf-8").write(json.dumps(document, indent=2))

    with pytest.raises(PreCommitmentError, match="do not match the handover record"):
        score(responses, gt, probes, skip_tier2=True, handover_path=str(handover))


def test_the_abort_names_both_digests_so_it_can_be_argued_with(tmp_path):
    responses, gt, probes = make_run(tmp_path)
    handover = tmp_path / "handover.json"
    committed = build_handover(probes=probes, ground_truth=gt)
    write_handover(handover, committed)

    open(gt, "a", encoding="utf-8").write("\n")

    with pytest.raises(PreCommitmentError) as caught:
        score(responses, gt, probes, skip_tier2=True, handover_path=str(handover))

    message = str(caught.value)
    assert committed.ground_truth.digest in message
    assert hash_file(gt) in message
    assert committed.created in message


def test_a_matching_ground_truth_is_recorded_as_verified(tmp_path):
    responses, gt, probes = make_run(tmp_path)
    handover = tmp_path / "handover.json"
    write_handover(handover, build_handover(probes=probes, ground_truth=gt))

    report = score(
        responses, gt, probes, skip_tier2=True, handover_path=str(handover)
    )
    pre = report["manifest"]["pre_commitment"]
    assert pre["status"] == "verified"
    assert pre["verified"] == ["ground_truth", "probes"]


def test_a_run_without_a_handover_claims_nothing_rather_than_implying_it(tmp_path):
    """Absent is a status, not a blank. A reader must be able to tell a run that was
    pre-committed from one that simply was not."""
    report = score(*make_run(tmp_path), skip_tier2=True)
    assert report["manifest"]["pre_commitment"]["status"] == "absent"


def test_the_corpus_digest_is_carried_and_says_so(tmp_path):
    """`score` reads no corpus (§5.1). The digest can only be one committed earlier,
    and a manifest that presented it as freshly computed would overclaim."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.txt").write_text("content\n")
    responses, gt, probes = make_run(tmp_path)

    handover = tmp_path / "handover.json"
    write_handover(
        handover,
        build_handover(corpus=str(corpus), probes=probes, ground_truth=gt),
    )

    manifest = score(
        responses, gt, probes, skip_tier2=True, handover_path=str(handover)
    )["manifest"]

    assert manifest["inputs"]["corpus_hash"] == hash_tree(corpus).digest
    assert "did not recompute" in manifest["inputs"]["corpus_hash_provenance"]
    assert manifest["pre_commitment"]["carried"] == ["corpus"]


# --------------------------------------------------------- the manifest has no holes


def test_every_section_6_5_field_is_populated_or_explained(tmp_path):
    """The F40 rule, applied to provenance instead of to checks.

    An omitted field and an unknown value read identically on the page, and they are
    different statements. This build cannot know the corpus mode or the seed; it says
    so, in the artefact, rather than leaving a reader to infer completeness.
    """
    manifest = score(*make_run(tmp_path), skip_tier2=True)["manifest"]
    assert unrecorded_gaps(manifest) == []


def test_the_gap_check_would_notice_an_unexplained_hole():
    """Negative control. A checker that cannot fail is not a checker."""
    assert "run.seed" in unrecorded_gaps({"run": {"seed": None}, "not_recorded": {}})
    assert "run.seed" not in unrecorded_gaps(
        {"run": {"seed": None}, "not_recorded": {"run.seed": "Phase D"}}
    )


def test_the_manifest_records_which_build_scored_the_run(tmp_path):
    manifest = score(*make_run(tmp_path), skip_tier2=True)["manifest"]
    tool = manifest["tool"]
    assert tool["version"]
    # In a checkout the sha is known; from an installed wheel it is not, and the
    # reason is recorded. Exactly one of those is true.
    assert bool(tool["commit_sha"]) != bool(tool["commit_unavailable"])


def test_the_signature_is_reported_for_the_reader_to_verify_not_by_us(tmp_path):
    """A signature this tool checked itself is evidence to nobody who is doubting the
    tool. The manifest states presence and hands over the command."""
    tool = score(*make_run(tmp_path), skip_tier2=True)["manifest"]["tool"]

    if tool["commit_sha"] is None:
        pytest.skip("not a git checkout")

    assert tool["commit_signature"] in ("present", "absent")
    if tool["commit_signature"] == "present":
        assert tool["commit_signature_verify_with"] == (
            f"git verify-commit {tool['commit_sha']}"
        )


def test_provenance_never_shells_out_to_a_signature_check():
    """`score` runs inside offline(), which patches this process's sockets and cannot
    see a child's. `git log --pretty=%G?` invokes gpg, and a gpg with
    auto-key-retrieve enabled fetches missing keys from a keyserver — a network path
    on the inside of the one claim (§5.1, F18) this project makes most loudly.

    So the rule is structural: the provenance layer runs only git commands that read
    local objects. This test is what keeps it that way when somebody later decides
    the manifest would look better saying 'verified'.
    """
    import ast
    from pathlib import Path

    import legal_rag_audit

    source = (
        Path(legal_rag_audit.__file__).parent / "provenance" / "tool.py"
    ).read_text(encoding="utf-8")

    invoked = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == "_git" and node.args:
            if isinstance(node.args[0], ast.Constant):
                invoked.add(node.args[0].value)

    assert invoked, "the AST walk found no git calls — it has stopped testing anything"
    # `log --show-signature`, `verify-commit` and `%G?` all reach gpg.
    assert invoked <= {"rev-parse", "cat-file", "status"}, (
        f"provenance/tool.py runs unexpected git subcommands: "
        f"{sorted(invoked - {'rev-parse', 'cat-file', 'status'})}. "
        f"Anything that verifies a signature invokes gpg in a child process, which "
        f"offline() cannot police."
    )


def test_the_manifest_states_the_instrument_behind_every_tier_2_number(tmp_path):
    """§4.1. A Tier 2 count is a statement about a model and a line; without both on
    the page it reads as a property of somebody's product."""
    manifest = score(*make_run(tmp_path), skip_tier2=True)["manifest"]
    recorded = {row["check"]: row for row in manifest["scoring"]["instruments"]}

    assert set(recorded) == set(BY_CHECK)
    for row in recorded.values():
        assert row["model"]
        assert isinstance(row["threshold"], float)
        assert row["threshold_source"]
        # Stated even when nothing was loaded — the manifest above was written by a
        # --skip-tier2 run, and a reader still needs to know what would have scored it.
        assert row["threshold_kind"]


def argument_default(module: str, method: str, argument: str):
    """Read a default argument out of an evaluator without importing it.

    By AST, deliberately. Importing these modules pulls sentence-transformers and
    therefore torch, and the whole reason instruments.py duplicates the model names is
    that the manifest must state them in an environment where that stack is absent
    (§5.3, F31). A drift check that only runs where torch is installed would not run
    in the place the duplication exists to serve.
    """
    import ast
    from pathlib import Path

    import legal_rag_audit

    source = (
        Path(legal_rag_audit.__file__).parent / "evaluators" / f"{module}.py"
    ).read_text(encoding="utf-8")

    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.FunctionDef) and node.name == method):
            continue
        args = node.args
        # Defaults align to the tail of the positional argument list.
        for name, default in zip(
            [a.arg for a in args.args][-len(args.defaults) :], args.defaults
        ):
            if name == argument:
                return ast.literal_eval(default)
    raise AssertionError(f"{module}.{method} has no argument {argument!r}")


def test_the_instrument_table_still_matches_the_evaluators():
    """The names are duplicated on purpose: the manifest must state them without
    importing torch. Duplication that nothing checks is drift with a delay."""
    assert argument_default("hallucination", "__init__", "model_name") == (
        ENTAILMENT_MODEL
    )
    assert argument_default("retrieval", "__init__", "model_name") == EMBEDDING_MODEL

    # Every instrument in the table is a check the registry actually registers as Tier 2.
    # A row left behind after a check moved tiers would put a model and a threshold on
    # the page for scoring that no longer runs one — which is the disclosure failure the
    # table exists to prevent, inverted.
    from legal_rag_audit.score.registry import tier2_checks

    assert sorted(BY_CHECK) == sorted(tier2_checks())


def test_the_drift_check_would_notice_a_renamed_model():
    """Negative control: the AST reader returns a real value, not None twice."""
    assert argument_default("retrieval", "__init__", "model_name") != ENTAILMENT_MODEL
    with pytest.raises(AssertionError):
        argument_default("retrieval", "__init__", "no_such_argument")


def test_the_manifest_says_what_the_response_file_did_not_carry(tmp_path):
    manifest = score(*make_run(tmp_path), skip_tier2=True)["manifest"]
    capture = manifest["capture"]

    assert capture["records"] > 0
    assert capture["document_ids_supplied"] is False
    # The fixture captures no upload manifest, so citation integrity cannot run — and
    # the manifest names it along with the reason, rather than leaving the reader to
    # find it in the body.
    assert "citation_integrity" in capture["checks_not_run"]
    assert "document_ids" in capture["checks_not_run"]["citation_integrity"]


def test_the_battery_composition_is_declared_not_derived_from_results(tmp_path):
    """F39. Denominators come from the probe file, and the manifest shows what they
    are made of — a no-correct-answer probe scores the opposite way round."""
    manifest = score(*make_run(tmp_path), skip_tier2=True)["manifest"]
    battery = manifest["battery"]
    probes = build_probes()

    assert battery["total_probes"] == len(probes)
    assert battery["positive_probes"] + battery["no_correct_answer_probes"] == len(
        probes
    )
    for check, count in battery["eligible_by_check"].items():
        assert count == sum(1 for p in probes if check in p.eligible_for)


# --------------------------------------------- F44: disclosure is a property of the tool


def test_every_run_writes_the_ground_truth_next_to_the_report(tmp_path):
    """§3.6 promises the withheld half arrives in full with the findings. A promise
    in a document is kept by whoever remembers; written by the tool, it is kept."""
    responses, gt, probes = make_run(tmp_path)
    out = tmp_path / "out"

    score(responses, gt, probes, skip_tier2=True, output_dir=str(out))

    assert (out / "report.json").exists()
    assert (out / "manifest.json").exists()
    assert (out / "ground_truth.json").exists()


def test_the_disclosed_copy_hashes_to_the_value_in_the_manifest(tmp_path):
    """The acceptance criterion for F44, and the reason the copy is byte-for-byte
    rather than re-serialised from the parsed model: the client verifies it against
    the manifest, and a reordered key would look like tampering."""
    responses, gt, probes = make_run(tmp_path)
    out = tmp_path / "out"

    report = score(responses, gt, probes, skip_tier2=True, output_dir=str(out))

    recorded = report["manifest"]["inputs"]["ground_truth_manifest_hash"]
    assert hash_file(out / "ground_truth.json") == recorded
    assert (out / "ground_truth.json").read_bytes() == open(gt, "rb").read()


def test_the_written_manifest_matches_the_one_inside_the_report(tmp_path):
    responses, gt, probes = make_run(tmp_path)
    out = tmp_path / "out"

    report = score(responses, gt, probes, skip_tier2=True, output_dir=str(out))

    written = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert written == report["manifest"]


def test_writing_into_the_directory_the_ground_truth_already_lives_in(tmp_path):
    """A rescore in place must not truncate the file it is copying from."""
    out = tmp_path / "out"
    out.mkdir()
    write_ground_truth(out / "ground_truth.json", build_ground_truth())
    responses, _, probes = make_run(tmp_path)

    report = score(
        responses,
        str(out / "ground_truth.json"),
        probes,
        skip_tier2=True,
        output_dir=str(out),
    )

    assert hash_file(out / "ground_truth.json") == (
        report["manifest"]["inputs"]["ground_truth_manifest_hash"]
    )


# ------------------------------------------------------------------- the CLI surface


def test_hash_with_nothing_to_hash_is_a_setup_error(capsys):
    from legal_rag_audit.cli import build_parser
    from legal_rag_audit.cli import EXIT_SETUP

    args = build_parser().parse_args(["hash"])
    assert args.func(args) == EXIT_SETUP


def test_hash_writes_a_record_that_score_accepts(tmp_path, capsys):
    """The two commands are one mechanism. If the record `hash` writes is not the
    record `score` reads, the pre-commitment is theatre."""
    from legal_rag_audit.cli import EXIT_FINDINGS, EXIT_OK, build_parser

    responses, gt, probes = make_run(tmp_path)
    handover = tmp_path / "handover.json"

    parser = build_parser()
    args = parser.parse_args(
        ["hash", "--probes", probes, "--ground-truth", gt, "-o", str(handover)]
    )
    assert args.func(args) == EXIT_OK
    capsys.readouterr()

    args = parser.parse_args(
        [
            "score",
            "--responses",
            responses,
            "--ground-truth",
            gt,
            "--probes",
            probes,
            "--handover",
            str(handover),
            "--skip-tier2",
            "-o",
            str(tmp_path / "out"),
        ]
    )
    assert args.func(args) in (EXIT_OK, EXIT_FINDINGS)

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report["manifest"]["pre_commitment"]["status"] == "verified"


def test_score_refuses_a_tampered_key_with_the_setup_exit_code(tmp_path):
    """Exit 2, not 1. A run that did not happen must not exit the way a run with
    findings does — CI cannot tell them apart otherwise."""
    from legal_rag_audit.cli import EXIT_SETUP, build_parser

    responses, gt, probes = make_run(tmp_path)
    handover = tmp_path / "handover.json"
    write_handover(handover, build_handover(probes=probes, ground_truth=gt))
    open(gt, "a", encoding="utf-8").write("\n")

    args = build_parser().parse_args(
        [
            "score",
            "--responses",
            responses,
            "--ground-truth",
            gt,
            "--probes",
            probes,
            "--handover",
            str(handover),
            "--skip-tier2",
            "-o",
            str(tmp_path / "out"),
        ]
    )
    assert args.func(args) == EXIT_SETUP
    assert not (tmp_path / "out").exists()


def test_the_handover_schema_is_published_like_every_other_contract():
    """A client verifying a record should not have to read our source to know its
    shape (F35)."""
    from legal_rag_audit.interchange import available_schemas, read_schema_document

    assert "handover.v1" in available_schemas()
    assert "run_manifest.v1" in available_schemas()
    document = read_schema_document("handover.v1")
    assert "schema" in document["required"]
    assert set(document["properties"]) >= {"corpus", "probes", "ground_truth"}


def test_the_instruments_table_is_not_empty():
    """Guards the assertions above from passing vacuously."""
    assert len(INSTRUMENTS) == 2


def test_a_handover_record_needs_no_artefacts_to_be_valid():
    """The model allows an empty record; the CLI is what refuses one. Kept separate
    so the schema stays permissive for future artefact types."""
    record = Handover(created="2026-08-02T00:00:00+00:00", tool_version="0.1.0")
    assert record.artefacts() == {}
