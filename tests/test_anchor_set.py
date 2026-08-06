"""What the anchor set has to be true of, and the matching rule it depends on.

`tests/test_external.py` covers the machinery — the pair logic, the evaluator, the store.
This file is about the *set*: how big it is, what it covers, and the two ways an anchor
can be wrong in a way that produces a finding against a system that answered correctly.

A false positive here is the worst output this tool can produce. It says, in a signed
report, that a named product returned a superseded statement of the law. §14.2 makes that
a release blocker, and every assertion below exists to catch one before a run does.
"""

import unicodedata

import pytest

from legal_rag_audit.evaluators._common import MATCH_RULE, normalise, present
from legal_rag_audit.external.anchors import ANCHORS, validate_anchors
from legal_rag_audit.external.battery import build_external_probes


def test_the_anchor_set_validates() -> None:
    validate_anchors()


def test_every_anchor_carries_two_readings_of_one_provision() -> None:
    for anchor in ANCHORS:
        assert len(anchor.readings) == 2, anchor.anchor_id
        assert anchor.readings[0].invariant != anchor.readings[1].invariant


def test_both_practice_areas_are_covered() -> None:
    """§20.1 item 3 asked for employment *and* commercial anchors.

    Employment shipped in Phase G and commercial did not, because the obvious candidate —
    Late Payment of Commercial Debts (Interest) Act 1998 s.4 — has no phrase that
    survives rule 2. The Companies Act accounting thresholds do.
    """
    topics = {anchor.topic for anchor in ANCHORS}
    assert "employment" in topics
    assert "commercial" in topics


def test_only_one_reading_in_the_whole_set_can_ever_change() -> None:
    """Every anchor after the first two is fully frozen, deliberately.

    A closed validity range cannot be amended again, so those anchors need no refresh
    ever. `era-108`'s second reading asks for the law as it stands, which is the more
    natural question and the one `ingest` exists to re-check. One live reading is enough
    to justify that command; more would be maintenance without additional argument.
    """
    live = [
        (anchor.anchor_id, reading.as_at)
        for anchor in ANCHORS
        for reading in anchor.readings
        if not reading.frozen
    ]
    assert live == [("era-108", None)], live


def test_no_invariant_is_a_substring_of_another_in_the_same_anchor() -> None:
    """`£36` inside `£360` would make the pair unscoreable.

    Containment is the matching rule, so an invariant that is a prefix of its sibling
    would be found in an answer carrying only the other one — and the pair is the test.
    """
    for anchor in ANCHORS:
        first, second = (normalise(r.invariant) for r in anchor.readings)
        assert first not in second and second not in first, anchor.anchor_id


@pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: a.anchor_id)
def test_neither_question_gives_away_either_answer(anchor) -> None:
    """Covered by `validate_anchors`, asserted here per anchor so a failure names one."""
    first, second = anchor.readings
    for reading, other in ((first, second), (second, first)):
        assert not present(reading.question, reading.invariant)
        assert not present(reading.question, other.invariant)


def test_the_battery_is_two_probes_per_anchor_plus_the_licensed_pair() -> None:
    probes = build_external_probes()
    assert len(probes) == 2 * len(ANCHORS) + 2


class TestTheMatchingRule:
    """`present` decides every Tier 1 finding. Its edges are the tool's edges."""

    def test_unicode_is_normalised_before_comparison(self) -> None:
        """NFC, and it is not cosmetic.

        `é` has two encodings, and they are different strings to `in`. Nothing in an
        English anchor notices. A French or Spanish one does: the phrase is typed into a
        file by a person and the answer arrives from an API that may have decomposed it,
        so the two would fail to match while looking identical on every screen either was
        read on — and the report would say the system returned the wrong version of the
        law against a system that returned the right one.
        """
        composed = "salarié à durée indéterminée"
        decomposed = unicodedata.normalize("NFD", composed)
        assert composed != decomposed
        assert present(decomposed, composed)
        assert present(composed, decomposed)

    def test_the_published_rule_says_so(self) -> None:
        """`MATCH_RULE` is printed beside every Tier 1 result. It has to be current."""
        assert "NFC" in MATCH_RULE

    def test_case_and_whitespace_still_fold(self) -> None:
        assert present("SHALL NOT   EXCEED  £464", "shall not exceed £464")

    def test_no_word_is_altered_by_folding(self) -> None:
        """`lower()` rather than `casefold()`, so ß does not silently become ss.

        The rule is published as one that never changes what was written; a fold that
        rewrites a German word would make that false.
        """
        assert normalise("Straße") != normalise("Strasse")

    @pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: a.anchor_id)
    def test_an_answer_carrying_only_the_other_reading_never_matches(self, anchor) -> None:
        """The pair only works if each phrase is genuinely absent from the other."""
        first, second = anchor.readings
        assert not present(second.invariant, first.invariant)
        assert not present(first.invariant, second.invariant)
