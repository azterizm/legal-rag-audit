"""Seeded plants, the collision guard, and the planting pipeline (§3.2, Phase D).

Tier 1's whole claim is *a planted token either appeared or it did not*. That sentence is
only true while three things hold, and each is tested here rather than assumed:

* the token is reproducible from the seed, so a third party can regenerate the battery;
* the token means exactly one thing, which is the collision guard's job;
* the guard fails loudly when it cannot do its job, rather than quietly reusing a value.
"""

import hmac
import re
from hashlib import sha256

import pytest

from legal_rag_audit.plants import (
    CHECKED,
    CITATION,
    DATE,
    ENTITY,
    FIGURE,
    KINDS,
    LABEL,
    NOT_CHECKED,
    PUBLISHED_DEMO_SEED,
    TEMPLATES,
    TOKEN,
    Guard,
    Minted,
    PlantError,
    PlantExhausted,
    PlantingError,
    mint,
    plant,
    unplanted,
    write_corpus,
)
from legal_rag_audit.plants.guard import MAX_ATTEMPTS
from legal_rag_audit.plants.register import is_real_party

SEED = "test-seed/v1"


# ------------------------------------------------------------------------ determinism


def test_a_plant_is_a_pure_function_of_its_four_inputs():
    """The property the whole disclosure model rests on. A client handed the seed at the
    end of an engagement regenerates the identical battery, or the handover proves
    nothing."""
    for kind in KINDS:
        first = mint(kind, SEED, "p-1")
        assert mint(kind, SEED, "p-1") == first
        assert mint(kind, SEED, "p-2") != first
        assert mint(kind, "other-seed", "p-1") != first
        assert mint(kind, SEED, "p-1", attempt=1) != first


def test_the_published_recipe_produces_the_same_stream_as_the_implementation():
    """The recipe in `mint.RECIPE` is what a third party reimplements from.

    Written out here by hand, from the prose rather than from the code: HMAC-SHA256 over
    `<plant_id>#<attempt>`, read as big-endian 32-bit integers, rejection-sampled. If the
    implementation drifts from the sentence we publish, somebody rebuilding the battery in
    another language gets different values and concludes we tampered with the corpus.
    """
    from legal_rag_audit.plants.mint import _Stream

    def independent(seed: str, label: str, n: int, draws: int) -> list[int]:
        key = seed.encode("utf-8")
        buffer = hmac.new(key, label.encode("utf-8"), sha256).digest()
        block = 0
        limit = (2**32 // n) * n
        out = []
        while len(out) < draws:
            while len(buffer) < 4:
                block += 1
                buffer += hmac.new(
                    key, f"{label}/{block}".encode("utf-8"), sha256
                ).digest()
            word, buffer = int.from_bytes(buffer[:4], "big"), buffer[4:]
            if word < limit:
                out.append(word % n)
        return out

    stream = _Stream(SEED, "p-1", 0)
    assert [stream.below(97) for _ in range(20)] == independent(SEED, "p-1#0", 97, 20)


def test_an_unknown_kind_is_refused_rather_than_guessed():
    with pytest.raises(PlantError, match="unknown plant kind"):
        mint("smell", SEED, "p-1")


# ------------------------------------------------------------------------------ shapes


def test_each_kind_produces_the_shape_it_promises():
    """The shapes are the paraphrase-invariance argument (§3.2), not decoration."""
    assert re.fullmatch(r"[A-Z][a-z]+ [A-Za-z ]+", mint(ENTITY, SEED, "e").value)
    assert re.fullmatch(r"[A-Z][a-z]+", mint(LABEL, SEED, "l").value)
    assert re.fullmatch(r"£[1-9],\d{3},\d{3}\.\d{2}", mint(FIGURE, SEED, "f").value)
    assert re.fullmatch(r"\d{1,2} [A-Z][a-z]+ \d{4}", mint(DATE, SEED, "d").value)
    assert re.fullmatch(
        r"[A-Z][a-z]+ v [A-Z][a-z]+ \[\d{4}\] EWHC \d{4} \([A-Za-z]+\)",
        mint(CITATION, SEED, "c").value,
    )
    assert re.fullmatch(r"ZX9-ACK-[0-9a-f]{8}", mint(TOKEN, SEED, "t").value)


def test_a_figure_never_has_a_leading_zero():
    """`£0,729,530.68` is not a figure anybody would write, and a plant that looks like
    a formatting bug invites the reply that the finding is one."""
    for n in range(400):
        assert not mint(FIGURE, SEED, f"f-{n}").value.startswith("£0,")


def test_generated_citations_sit_outside_the_range_real_ones_occupy():
    """The offline half of the real-world collision check. No division of the High Court
    has issued four thousand judgments in a year, so the number alone rules the citation
    out — a check that holds without a lookup, which matters because scoring never opens
    a socket."""
    for n in range(300):
        number = int(
            re.search(r"EWHC (\d+)", mint(CITATION, SEED, f"c-{n}").value).group(1)
        )
        assert number >= 4000


def test_coined_words_do_not_land_on_the_bundled_register_of_real_parties():
    for n in range(500):
        for part in mint(CITATION, SEED, f"c-{n}").parts:
            assert not is_real_party(part)


# ------------------------------------------------------------------------------- guard


def test_ten_thousand_generations_produce_no_collision():
    """§14's acceptance for Phase D, and Tier 1's integrity condition.

    Not merely *"the generator rarely repeats"* — the guard has to make repetition
    impossible, because a reused value makes two findings indistinguishable and the
    report attributes a leak to the wrong document.
    """
    guard = Guard.over({t.name: unplanted(t.body) for t in TEMPLATES})
    high_entropy = (ENTITY, LABEL, FIGURE, CITATION, TOKEN)

    seen: set[str] = set()
    for n in range(10_000):
        kind = high_entropy[n % len(high_entropy)]
        minted, _ = guard.mint(kind, SEED, f"bulk-{n}")
        assert minted.value not in seen
        seen.add(minted.value)

    assert len(seen) == 10_000
    assert len(guard.taken) == 10_000


def test_no_generated_value_occurs_in_the_corpus_as_authored():
    guard = Guard.over({t.name: unplanted(t.body) for t in TEMPLATES})
    corpus = "\n".join(unplanted(t.body) for t in TEMPLATES).lower()
    for n in range(1_000):
        minted, _ = guard.mint(ENTITY, SEED, f"bulk-{n}")
        assert minted.value.lower() not in corpus


def test_a_value_already_in_the_corpus_is_rejected():
    """A plant that occurs in the corpus fires on the corpus, not on a leak. A false
    positive, and §14.2 makes a false positive a release blocker."""
    guard = Guard.over({"d.txt": "The counterparty is Zathrex Holdings SARL."})
    reason = guard.reject(Minted(ENTITY, "Zathrex Holdings SARL", ("Zathrex",)))
    assert reason is not None and "already occurs in the corpus" in reason


def test_overlapping_plants_are_rejected_in_both_directions():
    """Presence is scored by substring, so if A contains B every hit on A is also a hit
    on B and the report names the wrong document."""
    guard = Guard.over({})
    guard.accept(Minted(LABEL, "Zathrex"), "p-1")

    contains = guard.reject(Minted(ENTITY, "Zathrex Holdings SARL", ()))
    assert contains is not None and "contains plant 'p-1'" in contains

    guard_two = Guard.over({})
    guard_two.accept(Minted(ENTITY, "Zathrex Holdings SARL"), "p-2")
    contained = guard_two.reject(Minted(LABEL, "Zathrex Holdings"))
    assert contained is not None and "contained by plant 'p-2'" in contained


def test_a_coined_word_matching_a_real_party_is_rejected():
    guard = Guard.over({})
    reason = guard.reject(
        Minted(CITATION, "Donoghue v Vrountuex [1994] EWHC 6497 (Pat)", ("Donoghue",))
    )
    assert reason is not None and "register of real parties" in reason


def test_a_citation_number_inside_the_real_range_is_rejected():
    """The claim on the report is enforced where it is stated, not left as a property of
    a constant three modules away."""
    guard = Guard.over({})
    reason = guard.reject(
        Minted(CITATION, "Zrearveex v Vrountuex [1994] EWHC 12 (Pat)", ("Zrearveex",))
    )
    assert reason is not None and "inside the range real citations use" in reason


def test_exhausting_a_value_space_aborts_loudly_rather_than_reusing_a_value():
    """`date` has the smallest space by nature — 28 x 12 x 46. A guard that ran out and
    silently returned a duplicate would break Tier 1 without anything failing."""
    guard = Guard.over({})
    # Take every value this plant id could reach, so no attempt can survive.
    for attempt in range(MAX_ATTEMPTS):
        guard.accept(mint(DATE, SEED, "d-1", attempt), f"other-{attempt}")

    with pytest.raises(PlantExhausted) as excinfo:
        guard.mint(DATE, SEED, "d-1")

    message = str(excinfo.value)
    assert "regenerations" in message
    assert "date" in message, "name the kind whose space ran out"
    assert "Aborting" in message


def test_the_guard_records_what_it_checked_and_what_it_could_not():
    """The scope of the guarantee, not the word 'guarded'. A reader told that no lookup
    left the machine can price the residual risk; a reader told nothing inherits ours."""
    record = Guard.over({}).record()
    assert record["checked"] == list(CHECKED)
    assert record["not_checked"] == list(NOT_CHECKED)
    assert any("no lookup leaves this machine" in n for n in record["not_checked"])
    assert record["plants"] == 0


def test_a_regeneration_is_a_recorded_event():
    guard = Guard.over({})
    forced = mint(LABEL, SEED, "p-1", 0)
    guard.accept(forced, "squatter")

    minted, attempt = guard.mint(LABEL, SEED, "p-1")
    assert attempt == 1
    assert minted.value != forced.value
    assert guard.record()["regenerations"] == 1
    assert "attempt 0" in guard.record()["regenerated"]["p-1"][0]


# ---------------------------------------------------------------------------- planting


def test_planting_fills_every_slot_and_leaves_no_marker_behind():
    corpus = plant(SEED)
    for body in list(corpus.documents.values()) + list(corpus.revisions.values()):
        assert "@@" not in body, "an unfilled slot ships the literal marker into a run"

    for p in corpus.plants:
        source = (
            corpus.revisions if p.state == "revision" else corpus.documents
        )[p.document]
        assert p.value in source, f"{p.plant_id} is in the answer key and not the corpus"


def test_every_plant_declares_where_it_was_inserted():
    """The client reading the disclosed key has to be able to find the plant in the
    document they were sent."""
    for p in plant(SEED).plants:
        assert p.location and len(p.location) > 5
        assert p.type in KINDS


def test_the_same_seed_gives_the_same_corpus_and_a_different_one_does_not():
    assert plant(SEED).documents == plant(SEED).documents
    assert plant(SEED).documents != plant("another-seed").documents


def test_the_published_demo_seed_is_labelled_as_such():
    """A report whose plants came from a published seed cannot claim they were
    unguessable, and this is what stops it claiming so by omission."""
    demo = plant()
    assert demo.seed == PUBLISHED_DEMO_SEED
    assert demo.is_demo()
    assert "reproducible by anyone" in demo.seed_source

    engagement = plant(SEED)
    assert not engagement.is_demo()
    assert engagement.seed_source == "supplied for this run"


def test_an_empty_seed_is_refused():
    with pytest.raises(PlantingError, match="empty"):
        plant("   ")


def test_a_slot_with_no_declared_plant_aborts(monkeypatch):
    """The body and the `slots` tuple disagreeing is a battery defect. It has to abort
    before the corpus is written, not produce a document with a marker in it."""
    from legal_rag_audit.plants import pipeline, templates

    broken = templates.Template(
        name="broken.txt", body="A value: @@nobody-declared-this@@\n", slots=()
    )
    monkeypatch.setattr(pipeline, "TEMPLATES", (broken,))
    with pytest.raises(PlantingError, match="no declared plant"):
        pipeline.plant(SEED)


def test_a_declared_plant_with_no_slot_aborts(monkeypatch):
    """The mirror image: minted, in the answer key, and nowhere in the corpus. The check
    against it would fail a correct system."""
    from legal_rag_audit.plants import pipeline, templates

    broken = templates.Template(
        name="broken.txt",
        body="Nothing here.\n",
        slots=(templates.Slot("orphan", LABEL, "nowhere"),),
    )
    monkeypatch.setattr(pipeline, "TEMPLATES", (broken,))
    with pytest.raises(PlantingError, match="no slot for them"):
        pipeline.plant(SEED)


def test_asking_for_a_plant_that_does_not_exist_aborts():
    with pytest.raises(PlantingError, match="no plant named"):
        plant(SEED).value("not-a-plant")


def test_every_planted_document_carries_the_invariant_types_section_3_2_requires():
    """At least three invariant types per document holding a positive expectation, one
    entity-shaped and one figure. A system that paraphrases a leaked clause still emits
    the counterparty name or the amount, because those *are* the payload — a single
    planted string would be defeated by rewording."""
    corpus = plant(SEED)
    by_document: dict[str, list[str]] = {}
    for p in corpus.plants:
        by_document.setdefault(p.document, []).append(p.type)

    # The tenant-B matter is the document the rule exists for: it is the one whose
    # contents a leak would paraphrase.
    kinds = by_document["tenant_b_matter.txt"]
    assert len(set(kinds)) >= 3
    assert ENTITY in kinds and FIGURE in kinds


def test_write_corpus_lays_out_both_states_where_hash_and_generate_expect_them(tmp_path):
    corpus = plant(SEED)
    written = write_corpus(tmp_path / "corpus", corpus)

    assert written["base"] == len(corpus.documents)
    assert written["revision"] == len(corpus.revisions)
    for name, body in corpus.documents.items():
        assert (tmp_path / "corpus" / "base" / name).read_text(encoding="utf-8") == body
    for name, body in corpus.revisions.items():
        assert (
            tmp_path / "corpus" / "revision" / name
        ).read_text(encoding="utf-8") == body


def test_the_revision_replaces_a_document_rather_than_adding_one():
    """Index freshness turns on the same document saying something different. A revision
    under a new filename would leave both values in the index and test nothing."""
    corpus = plant(SEED)
    assert set(corpus.revisions) <= set(corpus.documents)
    assert corpus.revisions, "the battery needs a revision or index freshness cannot run"
