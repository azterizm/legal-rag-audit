"""The corpus library (§9.5) — the spine, the loader, and every corpus that ships.

Phase H's claim is that a domain corpus is an *artefact somebody authors*, not code
somebody edits, and that the fifth one in a practice area is half a day because there is
nothing left to design by the time an author starts. Two things have to hold for that to
be true rather than aspirational, and both are tested here:

* **The spine decides the structure.** Every corpus fills the same roles, so the battery,
  the expectations and the check register are authored once. A corpus that omits a role,
  invents one, or leaves one unlocated does not load.
* **The loader says what is missing.** An author's inner loop is `plant --corpus <dir>`,
  and every refusal below names the thing to go and write. A validator that only said
  *invalid* would move the discovery to the first run against a live target, where a
  missing plant reads as a finding about somebody else's system (NF9).

The third property is the one that would be easiest to lose quietly: **a corpus must not
be able to score against something it does not contain.** Two checks here are about that
alone — an `out_of_corpus` phrase that turns out to be in a document, and a probe whose
wording quotes the answer it is scored on. Both would pass a system that retrieved
nothing, and §14.2 makes a false positive a release blocker.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from legal_rag_audit.corpora import (
    DEFAULT,
    MANDATORY,
    SKELETON,
    SPINE,
    CorpusSpecError,
    available,
    library_root,
    load,
)
from legal_rag_audit.corpora.spine import BY_KEY, REVISION, ROLES
from legal_rag_audit.plants import plant
from legal_rag_audit.probes.battery import BATTERY, build_ground_truth, build_probes

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED = "legal-rag-audit/corpora-test/v1"

SHIPPED = available()

#: Corpora built entirely from invented instruments. `staleness_triggers: []` is the
#: correct answer for these and a defect for a practice-area corpus, so they are named
#: here rather than letting the assertion be weakened for everyone.
#:
#: The distinction is *does this corpus state a position on real law*, not *is it a
#: demo* — `rag-probes-uk` is a working corpus that a paid run can use, and it is exempt
#: for the same reason `bundled-demo` is: Parliament cannot amend the Ravensbourne Act.
#: Nothing in the manifest schema expresses that today, which is why the list is here;
#: a third synthetic corpus is the point at which it should become a declared field.
NO_LEGAL_POSITION = {DEFAULT, "rag-probes-uk"}
DOMAIN_CORPORA = [name for name in SHIPPED if name not in NO_LEGAL_POSITION]


@pytest.fixture(scope="module")
def scratch(tmp_path_factory):
    """A writable copy of the bundled demo, for tests that break a corpus on purpose."""

    def make(name: str = DEFAULT) -> Path:
        target = tmp_path_factory.mktemp("corpus") / name
        shutil.copytree(Path(library_root(), name), target)
        return target

    return make


def _edit(path: Path, mutate) -> None:
    manifest = yaml.safe_load((path / "corpus.yaml").read_text(encoding="utf-8"))
    mutate(manifest)
    (path / "corpus.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")


# --------------------------------------------------------------------------- the spine


def test_the_shipped_library_is_not_empty():
    assert DEFAULT in SHIPPED
    assert DOMAIN_CORPORA, (
        "§9.5's economics rest on a library of practice-area corpora. A build shipping "
        "only the demo has the machinery and none of the asset."
    )


def test_the_skeleton_is_not_offered_as_a_corpus():
    """It is deliberately incomplete. Listing it would invite somebody to run it."""
    assert SKELETON not in SHIPPED
    assert Path(library_root(), SKELETON).is_dir()


def test_every_mandatory_element_is_in_the_spine_rather_than_in_a_convention():
    """§9.5 item 3 — mandatory *in every domain corpus*.

    A rule like that only means something if a corpus without it cannot load, so it is
    checked against the spine rather than against any one corpus: nothing an author does
    can produce a corpus missing a contradiction pair, because the pair is not theirs to
    leave out.
    """
    keys = {d.key for d in SPINE}
    for element, required in MANDATORY.items():
        assert set(required) <= keys, f"{element} has no document in the spine"


def test_a_document_below_the_invariant_floor_records_why():
    """§9.5 item 1 sets three invariants of two types. Five documents are below it.

    Every one is a case where a second invariant would give the question a second correct
    answer — which would fail a correct system. The reason is recorded beside the
    document rather than the rule being relaxed, so a sixth appearing without one is a
    build failure.
    """
    thin = [d for d in SPINE if len(d.roles) < 3]
    assert thin, "if this is empty the floor is no longer being exercised"
    for document in thin:
        assert document.thin_because, f"{document.key} is below the floor with no reason"


# ------------------------------------------------------------------ every shipped corpus


@pytest.mark.parametrize("name", SHIPPED)
def test_a_shipped_corpus_loads_plants_and_builds_its_battery(name):
    """The whole path, per corpus. A corpus that loads and cannot be planted is worse
    than one that does not load: the failure moves to the moment somebody is running an
    engagement."""
    corpus = load(name)
    planted = plant(SEED, corpus)

    assert len(planted.plants) == len(ROLES)
    assert planted.source.name == name

    probes = build_probes(corpus=planted)
    assert {p.probe_id for p in probes} == {e.probe_id for e in BATTERY}
    assert all(p.text.strip() for p in probes)

    ground_truth = build_ground_truth(planted)
    assert ground_truth.corpus is not None
    assert ground_truth.corpus.name == name
    assert ground_truth.corpus.digest == corpus.digest


@pytest.mark.parametrize("name", SHIPPED)
def test_no_probe_carries_a_planted_value_into_the_question(name):
    """A question that quotes its own answer is scored by echo.

    The loader refuses `{plant:...}` naming an expected invariant; this is the same
    property checked on the *resolved* text, after the values are substituted, which is
    what actually reaches the target.
    """
    planted = plant(SEED, load(name))
    ground_truth = build_ground_truth(planted)
    expected = {e.probe_id: e for e in ground_truth.expectations}

    for probe in build_probes(corpus=planted):
        expectation = expected.get(probe.probe_id)
        if expectation is None:
            continue
        for answer in expectation.must_contain:
            assert answer not in probe.text, (
                f"{name}: {probe.probe_id} quotes {answer!r}, which it is scored for "
                f"containing. The check would pass a system that retrieved nothing."
            )


@pytest.mark.parametrize("name", SHIPPED)
def test_the_out_of_corpus_lure_is_genuinely_absent(name):
    """§8.2 #6 is scored by absence, so absence is the thing to check.

    A phrase that turned out to be in a document would record a system quoting its own
    corpus as having answered from its weights — a false positive against a correct
    system, which is a release blocker.
    """
    corpus = load(name)
    assert corpus.out_of_corpus
    haystack = "\n".join(d.body for d in corpus.documents).lower()
    for phrase in corpus.out_of_corpus:
        assert phrase.lower() not in haystack


@pytest.mark.parametrize("name", DOMAIN_CORPORA)
def test_a_domain_corpus_names_what_would_date_it(name):
    """§9.5 — corpora go stale because law moves, and that is the monitoring retainer.

    The demo is exempt and says so in its own manifest: it states no legal position, so
    there is nothing an amendment could reach. A *practice-area* corpus with an empty
    list has not answered the question.
    """
    corpus = load(name)
    assert corpus.staleness_triggers, (
        f"{name} declares no staleness trigger. A corpus in a practice area is stated as "
        f"at a date, and the re-run trigger is what makes a monitoring retainer a real "
        f"product rather than a repackaged one-off."
    )
    for trigger in corpus.staleness_triggers:
        assert trigger.instrument.strip() and trigger.invalidates.strip()


def test_two_corpora_ask_different_questions_of_the_same_checks():
    """The point of the library, stated as an assertion.

    Same checks, same roles, same expectations by construction — and questions worded for
    the practice area, because *what is the aggregate liability limit in the supplier
    agreement* retrieves nothing from an employment index.
    """
    if len(DOMAIN_CORPORA) < 2:
        pytest.skip("needs two domain corpora")

    first, second = (load(n) for n in DOMAIN_CORPORA[:2])
    assert set(first.probes) == set(second.probes)
    differing = [k for k in first.probes if first.probes[k] != second.probes[k]]
    assert len(differing) == len(first.probes), (
        f"{len(first.probes) - len(differing)} question(s) are worded identically across "
        f"two practice areas. That is a scaffold left unedited, not a coincidence."
    )
    assert first.digest != second.digest


# ------------------------------------------------------------------------- the skeleton


def test_the_skeleton_refuses_to_load():
    with pytest.raises(CorpusSpecError, match="placeholder"):
        load(str(Path(library_root(), SKELETON)))


def test_the_skeleton_matches_what_the_generator_produces(tmp_path):
    """Regenerated, not copied — so adding a role to the spine breaks the build.

    A skeleton that had drifted would scaffold a corpus missing the new document, and the
    author would discover it from a validation error rather than from the template. That
    is exactly the discovery this phase exists to move earlier.
    """
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "new_corpus.py"),
         SKELETON, "-o", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    generated = tmp_path / SKELETON
    committed = Path(library_root(), SKELETON)

    def tree(root: Path) -> dict[str, str]:
        return {
            str(p.relative_to(root)): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    assert tree(generated) == tree(committed), (
        "corpora/library/TEMPLATE/ has drifted from scripts/new_corpus.py. Regenerate it: "
        "rm -rf src/legal_rag_audit/corpora/library/TEMPLATE && "
        "python3 scripts/new_corpus.py TEMPLATE"
    )


# ------------------------------------------------------------------------- refusals
#
# One per way an author can get it wrong. Each asserts the *diagnosis*, not merely that
# something was raised — the message is the deliverable, because it is what turns
# authoring a corpus into a loop rather than an investigation.


def test_a_missing_slot_in_the_body_names_the_marker_to_write(scratch):
    path = scratch()
    body = path / "documents" / "supplier_agreement_v1.txt"
    body.write_text(body.read_text().replace("@@contra-v1@@", "£1,000,000"), encoding="utf-8")

    with pytest.raises(CorpusSpecError) as excinfo:
        load(str(path))
    assert "@@contra-v1@@" in str(excinfo.value)


def test_a_slot_the_spine_does_not_declare_is_refused(scratch):
    path = scratch()
    body = path / "documents" / "statute_alpha.txt"
    body.write_text(body.read_text() + "\nAlso: @@invented-plant@@\n", encoding="utf-8")

    with pytest.raises(CorpusSpecError, match="invented-plant"):
        load(str(path))


def test_a_slot_with_no_recorded_location_is_refused(scratch):
    path = scratch()
    _edit(path, lambda m: m["documents"]["statute_alpha"]["slots"].clear())

    with pytest.raises(CorpusSpecError) as excinfo:
        load(str(path))
    message = str(excinfo.value)
    assert "disamb-alpha" in message and "location" in message


def test_an_unworded_probe_is_refused(scratch):
    path = scratch()
    _edit(path, lambda m: m["probes"].pop("attr-001"))

    with pytest.raises(CorpusSpecError) as excinfo:
        load(str(path))
    assert "attr-001" in str(excinfo.value)


def test_a_probe_the_battery_does_not_ask_is_refused(scratch):
    path = scratch()
    _edit(path, lambda m: m["probes"].update({"made-up-001": "Anything at all?"}))

    with pytest.raises(CorpusSpecError, match="made-up-001"):
        load(str(path))


def test_a_probe_quoting_its_own_answer_is_refused(scratch):
    path = scratch()
    _edit(
        path,
        lambda m: m["probes"].update(
            {"contra-001": "Is the liability cap {plant:contra-v1}?"}
        ),
    )

    with pytest.raises(CorpusSpecError) as excinfo:
        load(str(path))
    assert "quotes the answer" in str(excinfo.value)


def test_a_probe_may_name_an_identifier_it_cannot_retrieve_without(scratch):
    """The other side of the same rule, and the reason it is not simply *no plants in
    questions*: you cannot ask about a support band without naming the band."""
    path = scratch()
    corpus = load(str(path))
    assert "{plant:struct-band}" in corpus.probes["struct-001"]


def test_an_out_of_corpus_phrase_that_is_in_a_document_is_refused(scratch):
    path = scratch()
    body = path / "documents" / "authority_digest.txt"
    body.write_text(
        body.read_text() + "\nSee also Donoghue v Stevenson.\n", encoding="utf-8"
    )

    with pytest.raises(CorpusSpecError) as excinfo:
        load(str(path))
    assert "Donoghue v Stevenson" in str(excinfo.value)
    assert "false positive" in str(excinfo.value)


def test_a_missing_staleness_key_is_refused_but_an_empty_list_is_not(scratch):
    """The key is required so that *no triggers* is a decision rather than an omission."""
    path = scratch()
    _edit(path, lambda m: m.pop("staleness_triggers"))
    with pytest.raises(CorpusSpecError, match="staleness_triggers"):
        load(str(path))

    _edit(path, lambda m: m.update({"staleness_triggers": []}))
    assert load(str(path)).staleness_triggers == ()


def test_a_document_key_the_spine_does_not_have_is_refused(scratch):
    path = scratch()
    _edit(
        path,
        lambda m: m["documents"].update(
            {"extra_document": {"filename": "x.txt", "identifier": "X", "slots": {}}}
        ),
    )
    with pytest.raises(CorpusSpecError, match="extra_document"):
        load(str(path))


def test_a_revision_block_is_required_for_the_document_that_gets_replaced(scratch):
    path = scratch()
    _edit(path, lambda m: m["documents"]["fee_notice"].pop("revision"))

    with pytest.raises(CorpusSpecError) as excinfo:
        load(str(path))
    message = str(excinfo.value)
    assert "revision" in message
    assert BY_KEY[("fee_notice", REVISION)].purpose.split(".")[0][:20] in message


def test_a_version_that_is_not_a_positive_integer_is_refused(scratch):
    path = scratch()
    _edit(path, lambda m: m.update({"version": "one"}))
    with pytest.raises(CorpusSpecError, match="version"):
        load(str(path))


# --------------------------------------------------------------------------- the digest


def test_the_digest_covers_the_documents_and_not_only_the_manifest(scratch):
    """§9.5 item 4 — the version goes on the attestation and the hash goes in the
    manifest. A digest that moved only when somebody remembered to bump `version` would
    let two different corpora report as the same one."""
    path = scratch()
    before = load(str(path)).digest

    body = path / "documents" / "statute_beta.txt"
    body.write_text(body.read_text() + "\nRule 6. Added.\n", encoding="utf-8")
    after = load(str(path)).digest

    assert before != after


def test_the_digest_is_stable_across_reads():
    assert load(DEFAULT).digest == load(DEFAULT).digest


def test_the_published_demo_corpus_is_reproducible_from_its_seed():
    """The bundled corpus is the one anyone can regenerate, and it has to keep being the
    same one — a report from the published seed is checkable only if the corpus behind it
    has not moved."""
    first, second = plant(), plant()
    assert first.documents == second.documents
    assert first.values == second.values
    assert first.source.digest == second.source.digest
