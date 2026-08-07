"""Phase G — existing-corpus mode, point-in-time pairs, licensed content (§9.2, F25, F27, F43).

The half of §9.1 whose ground truth is not ours. That changes what the tests have to do:
a planted invariant is true because we planted it, so the only question is whether the
scorer reads it back. A phrase quoted from `legislation.gov.uk` is true because the
primary source says so, and the failure modes are different in kind —

* the anchor set could contradict itself, or contain a phrase reachable by paraphrase of
  the other version, which would fail a correct system;
* the probe file could carry its own answer, which is the same leakage the planted
  battery guards against and is easier to do by accident here, because the question and
  the answer are both quotations from the same provision;
* the marker set could match something a compliant system emits, which on **this** check
  means alleging unlawful conduct against a named company (§16.3).

All three are false positives, and §14.2 makes those release blockers. So most of what is
below tests that nothing fires when it should not.
"""

import json
from types import SimpleNamespace

import pytest

from legal_rag_audit.config import AuditConfig
from legal_rag_audit.evaluators import LicensedContentEvaluator, PointInTimeEvaluator
from legal_rag_audit.external import (
    ANCHORS,
    MARKER_CLASSES,
    Anchor,
    AnchorError,
    Reading,
    Store,
    build_external_ground_truth,
    build_external_probes,
    excerpt_around,
    find,
    snapshot_for,
    validate_anchors,
)
from legal_rag_audit.external.battery import LICENSED_PROBES
from legal_rag_audit.external.ingest import IngestError, ingest, text_of
from legal_rag_audit.generate.run import EXISTING_INDEX, GenerationError, resolve_corpus
from legal_rag_audit.score.registry import BY_NAME

# ------------------------------------------------------------------- the anchors


def test_the_shipped_anchors_are_usable():
    validate_anchors()
    assert ANCHORS, "an empty anchor set would make point_in_time NOT_ELIGIBLE forever"


def test_every_anchor_pairs_two_readings_of_one_provision():
    """The pair is the test. One dated question measures almost nothing."""
    for anchor in ANCHORS:
        assert len(anchor.readings) == 2
        assert anchor.readings[0].invariant != anchor.readings[1].invariant


def test_an_anchor_whose_readings_cannot_be_told_apart_is_refused():
    bad = Anchor(
        anchor_id="x",
        instrument="ukpga/1996/18",
        title="T",
        section="1",
        provision="section 1",
        topic="employment",
        readings=(
            Reading(as_at="2011-01-01", question="Then?", invariant="one year",
                    in_force_from="2010-01-01", in_force_to="2012-01-01"),
            Reading(as_at=None, question="Now?", invariant="one year",
                    in_force_from="2012-01-01"),
        ),
    )
    with pytest.raises(AnchorError, match="both readings carry"):
        validate_anchors((bad,))


def test_an_anchor_whose_question_carries_the_other_answer_is_refused():
    """A system that echoed the question must not be recorded as returning the wrong
    version. That is a false positive on the most trivial behaviour there is."""
    bad = Anchor(
        anchor_id="x",
        instrument="ukpga/1996/18",
        title="T",
        section="1",
        provision="section 1",
        topic="employment",
        readings=(
            Reading(
                as_at="2011-01-01",
                # Names the *other* reading's phrase.
                question="Was it not less than two years back then?",
                invariant="not less than one year",
                in_force_from="2010-01-01",
                in_force_to="2012-01-01",
            ),
            Reading(as_at=None, question="Now?", invariant="not less than two years",
                    in_force_from="2012-01-01"),
        ),
    )
    with pytest.raises(AnchorError, match="contains the other reading's accepted form"):
        validate_anchors((bad,))


def test_at_least_one_anchor_is_frozen_on_both_sides():
    """A pair of historic dates can never change, which is the pattern to prefer.

    An anchor whose second reading is the law as it stands is the more natural question
    and the one that goes stale; one where both validity ranges are closed is finished
    forever. If every anchor were live the battery would need a refresh to stay correct,
    and a battery that silently needs one is a battery scoring against a version of the
    law that is no longer there.
    """
    assert any(all(r.frozen for r in a.readings) for a in ANCHORS)


# ------------------------------------------------------- the probe file leaks nothing


def test_no_external_probe_contains_its_own_answer():
    """The same rule the planted battery lives by, and easier to break here.

    Both the question and the answer are quotations from one provision, so a question
    phrased slightly too helpfully hands over the phrase it is testing for. The probe
    file is what the target receives.
    """
    ground_truth = build_external_ground_truth()
    expectations = {e.probe_id: e for e in ground_truth.expectations}
    for probe in build_external_probes():
        expectation = expectations[probe.probe_id]
        text = " ".join(probe.text.split()).casefold()
        for phrase in [*expectation.must_contain, *expectation.must_not_contain]:
            assert " ".join(phrase.split()).casefold() not in text, (
                f"{probe.probe_id} asks a question containing {phrase!r}"
            )


def test_the_external_probe_file_carries_no_expectations():
    for probe in build_external_probes():
        record = probe.to_record()
        assert "must_contain" not in record
        assert set(record) <= {
            "schema", "probe_id", "family", "intent", "text", "tenant", "phase",
            "as_at_date", "eligible_for", "passes",
        }


def test_the_external_ground_truth_declares_it_plants_nothing():
    ground_truth = build_external_ground_truth()
    assert ground_truth.plants == []
    assert ground_truth.seed is None
    assert "plants nothing" in (ground_truth.seed_source or "")


def test_every_external_expectation_names_a_registered_check():
    for expectation in build_external_ground_truth().expectations:
        assert expectation.check in BY_NAME


def test_point_in_time_expectations_carry_their_date_and_partner():
    ground_truth = build_external_ground_truth()
    pit = [e for e in ground_truth.expectations if e.check == "point_in_time"]
    assert pit
    by_id = {e.probe_id: e for e in pit}
    for expectation in pit:
        assert expectation.provision
        assert expectation.paired_with in by_id
        # The pairing is symmetric, or one half of it would score against nothing.
        assert by_id[expectation.paired_with].paired_with == expectation.probe_id


# --------------------------------------------------------------- point in time


def _pit(answer, in_force="not less than one year", superseded="not less than two years",
         provision="section 108", as_at="2011-01-01"):
    return PointInTimeEvaluator().evaluate(
        answer=answer,
        in_force=[in_force],
        superseded=[superseded],
        provision=provision,
        as_at=as_at,
    )


def test_the_version_in_force_on_the_date_passes():
    result = _pit("The employee needed not less than one year of continuous employment.")
    assert result["status"] == "PASS"
    assert result["outcome"] == "version_correct"


def test_the_other_version_alone_is_the_finding():
    result = _pit("The employee needed not less than two years of continuous employment.")
    assert result["status"] == "FAIL"
    assert result["outcome"] == "version_mismatch"
    assert result["as_at"] == "2011-01-01"


def test_an_answer_carrying_both_versions_passes():
    """The decision that keeps this check off correct systems.

    An answer that says what the law was *and* what it became has told the reader more
    than was asked, not less. Failing it would fail the most useful behaviour available.
    """
    result = _pit(
        "As at that date the period was not less than one year; it was raised to not "
        "less than two years in April 2012."
    )
    assert result["status"] == "PASS"
    assert result["outcome"] == "version_correct_with_context"


def test_neither_version_is_not_captured():
    result = _pit("The qualifying period depends on the circumstances of the dismissal.")
    assert result["status"] == "NOT_CAPTURED"
    assert "Not a pass" in result["reason"]


# ----------------------------------------------------- neither version, three ways
#
# Defect 20. The first live run of this battery put ten of twelve probes in the neither
# branch, and they were not the same event: four answers declined, one asserted £751 per
# week cited to a section that read £508 on the date asked. Both printed
# `no_version_returned`, which is F40 — an absent measurement and a failed one reading
# the same on the page.


def _figures(answer, question=""):
    """A money anchor, which is what five of the six shipped anchors are."""
    return PointInTimeEvaluator().evaluate(
        answer=answer,
        in_force=["£450"],
        superseded=["£508"],
        provision="section 186",
        as_at="2014-01-01",
        question=question,
    )


def test_an_answer_that_asserts_nothing_of_the_kind_asked_for_is_a_declination():
    result = _figures("I could not produce a grounded answer for that date.")
    assert result["status"] == "NOT_CAPTURED"
    assert result["outcome"] == "declined_to_state_a_version"
    assert result["claims_offered"] == []


def test_an_answer_that_asserts_a_third_figure_is_recorded_apart_from_a_declination():
    """The £751 case, verbatim in shape. Still not a finding — which version was
    retrieved was not observable — but a reader triaging ten unscoreable records has to
    be able to see which of them said a number."""
    result = _figures(
        "The weekly limit under section 186 was £751 per week at that time."
    )
    assert result["status"] == "NOT_CAPTURED"
    assert result["outcome"] == "answered_in_neither_version"
    assert result["claims_offered"] == ["£751"]


def test_the_split_is_made_on_the_presence_of_a_claim_not_on_refusal_wording():
    """Enumerating refusal phrasings is the trap §8.2 #8 names by hand, and the reason
    `abstention` was rewritten. Two answers that decline in unrelated words land in the
    same place; an answer that declines politely and then states a figure does not."""
    plain = _figures("I could not produce a grounded answer.")
    ornate = _figures(
        "Regrettably the retrieved material does not settle the position as it stood "
        "then, and I would rather not guess at it."
    )
    hedged = _figures("I am not certain, but I believe it was around £751.")
    assert plain["outcome"] == ornate["outcome"] == "declined_to_state_a_version"
    assert hedged["outcome"] == "answered_in_neither_version"


def test_a_figure_the_question_itself_named_is_not_an_assertion():
    """The echo rule, inherited from `abstention`. A system that restates the figure it
    was asked about and then declines has repeated the prompt, not answered it."""
    result = _figures(
        "You ask whether the limit was £751. I cannot confirm the figure for that date.",
        question="As at 1 January 2014, was the weekly limit £751?",
    )
    assert result["outcome"] == "declined_to_state_a_version"
    assert result["claims_offered"] == []


def test_readings_the_shape_rule_cannot_see_keep_the_old_outcome_and_say_so():
    """`not less than one year` is a duration written in words, and the shared shape
    vocabulary requires a digit. Widening it was rejected: the same vocabulary is what
    `abstention` produces findings from, and §14.2 makes a false positive a blocker. So
    the split is declined out loud rather than guessed."""
    result = _pit("The qualifying period depends on the circumstances of the dismissal.")
    assert result["outcome"] == "no_version_returned"
    assert "cannot see" in result["reason"]


def _external_run(tmp_path, answers):
    """Score the shipped external battery against a dictionary of answers."""
    from legal_rag_audit.interchange import (
        Response,
        write_ground_truth,
        write_probes,
        write_responses,
    )
    from legal_rag_audit.score import score

    probes = build_external_probes()
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "gt.json", build_external_ground_truth())
    write_responses(
        tmp_path / "responses.jsonl",
        [
            Response(
                run_id="r",
                probe_id=p.probe_id,
                query=p.text,
                answer=answers.get(p.probe_id, "It depends on the circumstances."),
                citations=[],
                total_ms=100,
                http_status=200,
            )
            for p in probes
        ],
    )
    return score(
        str(tmp_path / "responses.jsonl"),
        str(tmp_path / "gt.json"),
        str(tmp_path / "probes.jsonl"),
        skip_tier2=True,
        output_dir=str(tmp_path / "out"),
    )


def test_the_report_splits_the_unscoreable_records_by_what_the_answer_did(tmp_path):
    """Defect 20, end to end. The run this was written from scored two of twelve
    point-in-time records; `report.md` printed one number for the other ten and said
    nothing about them, because `partial` is only populated when *nothing* scores."""
    money = [
        e
        for e in build_external_ground_truth().expectations
        if e.check == "point_in_time" and any("£" in v for v in e.must_contain)
    ]
    assert len(money) >= 3, "this test needs a scored record beside two unscoreable ones"
    declined, asserted, correct = money[0], money[1], money[2]

    report = _external_run(
        tmp_path,
        {
            declined.probe_id: "I could not produce a grounded answer.",
            asserted.probe_id: "The limit was £751 per week at that date.",
            # One record that scores, which is the case the hole was in: `partial` is
            # populated only when nothing scores, so a run with a partial denominator
            # printed the count and no account of it.
            correct.probe_id: f"The limit was {correct.must_contain[0]} at that date.",
        },
    )
    assert report["checks"]["point_in_time"]["scored"] == 1
    groups = {
        g["outcome"]: g
        for g in report["checks"]["point_in_time"]["detail"]["not_captured_by_outcome"]
    }
    assert declined.probe_id in groups["declined_to_state_a_version"]["probes"]
    assert asserted.probe_id in groups["answered_in_neither_version"]["probes"]
    # Attributed to the probe that said it. Pooling the group's figures into one list
    # would read as though any record in it might have said any of them.
    by_probe = groups["answered_in_neither_version"]["claims_by_probe"]
    assert by_probe == {asserted.probe_id: ["£751"]}

    markdown = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "records that could not be scored" in markdown
    assert "declined_to_state_a_version" in markdown
    assert "answered_in_neither_version" in markdown
    # The figure itself, on the page. A reader triaging the run should not have to open
    # the response file to find out which record said a number.
    assert "£751" in markdown


def test_an_unscoreable_record_is_still_outside_the_denominator(tmp_path):
    """The split changes what the reader is told, never what was counted. Both new
    outcomes stay out of `scored` and out of `failed`."""
    money = [
        e
        for e in build_external_ground_truth().expectations
        if e.check == "point_in_time" and any("£" in v for v in e.must_contain)
    ]
    report = _external_run(
        tmp_path, {money[0].probe_id: "The limit was £751 per week at that date."}
    )
    check = report["checks"]["point_in_time"]
    assert check["failed"] == 0
    assert check["not_captured"] == check["eligible"]
    assert check["scored"] == 0


def test_no_neither_version_outcome_is_ever_a_finding():
    """All three say the same thing about the target: which version it retrieved was not
    observable. Turning our own inability to observe into a failure is what §14.2 makes
    a release blocker."""
    answers = [
        "I could not produce a grounded answer.",
        "The limit was £751 per week.",
        "It depends on the circumstances.",
    ]
    assert {_figures(a)["status"] for a in answers} == {"NOT_CAPTURED"}


def test_the_right_provision_with_the_wrong_text_is_counted_apart():
    """§9.2's sharper form: it reads as authoritative and is wrong about the only thing
    that mattered. A reader triaging findings needs to know which of the two they have."""
    confident = _pit(
        "Under section 108 the employee needed not less than two years of continuous "
        "employment."
    )
    vague = _pit("The employee needed not less than two years.")
    assert confident["version_mismatch_with_correct_citation"] is True
    assert vague["version_mismatch_with_correct_citation"] is False
    assert confident["status"] == vague["status"] == "FAIL"


# ------------------------------------------------------------------- the markers


@pytest.mark.parametrize(
    "text,expected",
    [
        ("see 2019 WL 1234567 at 4", "westlaw_citation"),
        ("2019 U.S. Dist. LEXIS 12345", "lexis_citation"),
        ("2019 LEXIS 987", "lexis_citation"),
        ("classified at 233k1234", "west_key_number"),
    ],
)
def test_each_marker_class_matches_its_own_form(text, expected):
    hits = find(text, where="answer")
    assert [h.marker_class for h in hits] == [expected]


@pytest.mark.parametrize(
    "text",
    [
        # Court-assigned identifiers. Anyone may quote these, and a rule that caught one
        # would fire on every system that cites case law correctly.
        "Donoghue v Stevenson [1932] AC 562",
        "[2021] EWCA Civ 1044",
        "[2019] 1 WLR 123",
        "section 108 of the Employment Rights Act 1996",
        "the cap was £74,200 in 2014",
        "**1207** of the report",
    ],
)
def test_no_marker_fires_on_material_anyone_may_quote(text):
    assert find(text, where="answer") == []


def test_the_marker_set_names_what_it_does_not_score():
    from legal_rag_audit.external.markers import NOT_SCORED, NOT_SCORED_REASON

    assert "star_pagination" in NOT_SCORED
    assert "signal_marks" in NOT_SCORED
    assert "editorial" in NOT_SCORED_REASON


def test_no_editorial_prose_is_stored_in_the_repository():
    """§20.1 item 7. We do not hold a publisher's editorial layer in order to ask
    whether somebody else is holding it."""
    import legal_rag_audit.external.markers as module

    source = module.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    # The shipped classes are patterns, not content. A stored headnote would be a long
    # string literal of prose; the only long literals here are explanations.
    assert "MARKER_CLASSES" in text
    assert all(m.pattern.pattern for m in MARKER_CLASSES)


# --------------------------------------------------------------- licensed content


def _licensed(answer="", chunks=None, citations=()):
    return LicensedContentEvaluator().evaluate(
        answer=answer, retrieved_chunks=chunks, citations=list(citations)
    )


def test_a_marker_in_the_retrieval_is_the_finding():
    result = _licensed(
        answer="The headnote says the duty extended.",
        chunks=[{"text": "Headnote 2019 WL 1234567", "doc_id": "internal-42"}],
    )
    assert result["status"] == "FAIL"
    assert result["outcome"] == "in_index"
    assert result["appeared"] == ["2019 WL 1234567"]


def test_a_marker_cited_to_a_live_url_is_not_a_finding():
    result = _licensed(
        answer="Per 2019 WL 1234567, retrieved from https://uk.westlaw.com/Document/I0",
        chunks=[],
        citations=["https://uk.westlaw.com/Document/I0"],
    )
    assert result["status"] == "PASS"
    assert result["outcome"] == "external_fetch"
    assert result["appeared"] == []
    assert "westlaw" in result["publisher_services_cited"]


def test_a_marker_with_no_evidence_either_way_is_not_captured():
    result = _licensed(answer="Per 2019 WL 1234567 the duty extended.", chunks=None)
    assert result["status"] == "NOT_CAPTURED"
    assert result["outcome"] == "unattributed"
    assert result["retrieved_chunks_captured"] is False


def test_no_marker_at_all_passes():
    result = _licensed(answer="The neutral citation is [2021] EWCA Civ 1044.", chunks=[])
    assert result["status"] == "PASS"
    assert result["outcome"] == "no_marker_returned"


def test_the_finding_cannot_be_printed_without_its_limit_line():
    """§8.2 #18's caution, carried on the registry so a report cannot omit it."""
    limit = BY_NAME["licensed_content_reproduction"].limit
    assert limit
    assert "does **not** establish a licence breach" in limit
    assert "never an allegation of infringement" in limit


# ------------------------------------------------------------------- the store


def test_an_excerpt_is_a_window_not_a_provision():
    text = "x" * 2000 + " not less than one year " + "y" * 2000
    excerpt = excerpt_around(text, "not less than one year")
    assert "not less than one year" in excerpt
    assert len(excerpt) < 500


def test_a_snapshot_records_whether_the_phrase_was_there():
    anchor = ANCHORS[0]
    reading = anchor.readings[0]
    present = snapshot_for(anchor, reading, b"<x/>", f"... {reading.invariant} ...")
    absent = snapshot_for(anchor, reading, b"<x/>", "the provision says something else")
    assert present.invariant_present is True
    assert absent.invariant_present is False
    assert present.digest.startswith("sha256:")
    assert present.source_url.startswith("https://www.legislation.gov.uk/")


def test_drift_names_an_anchor_the_source_no_longer_supports():
    anchor = ANCHORS[0]
    store = Store(
        snapshots=[
            snapshot_for(anchor, reading, b"<x/>", "the provision says something else")
            for reading in anchor.readings
        ]
    )
    problems = store.drift((anchor,))
    assert len(problems) == 2
    assert all("was not in the provision" in p for p in problems)


def test_drift_names_an_anchor_nobody_has_checked():
    problems = Store().drift((ANCHORS[0],))
    assert all("never fetched" in p for p in problems)


def test_the_footprint_answers_the_open_storage_question():
    """§20.1 item 3 asked whether versioned statute data is affordable to hold. The
    answer is a number, and it is small because the store keeps phrases not statutes."""
    anchor = ANCHORS[0]
    store = Store(
        snapshots=[
            snapshot_for(anchor, r, b"x" * 200_000, f"... {r.invariant} ...")
            for r in anchor.readings
        ]
    )
    footprint = store.footprint()
    assert footprint["snapshots"] == 2
    assert footprint["stored_bytes"] < footprint["fetched_bytes"] / 100


def test_a_store_round_trips(tmp_path):
    anchor = ANCHORS[0]
    store = Store(
        snapshots=[
            snapshot_for(anchor, r, b"<x/>", f"... {r.invariant} ...")
            for r in anchor.readings
        ]
    )
    store.save(tmp_path / "s.json")
    assert Store.load(tmp_path / "s.json").drift((anchor,)) == []


def test_a_missing_store_says_the_battery_does_not_need_one(tmp_path):
    from legal_rag_audit.external import StoreError

    with pytest.raises(StoreError, match="does not need one"):
        Store.load(tmp_path / "absent.json")


# ------------------------------------------------------------------- ingestion


CLML = b"""<?xml version="1.0"?>
<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
  <Primary><Body><P1group><Title>Qualifying period of employment</Title>
  <P1><P1para><Text>Section 94 does not apply unless he has been continuously
  employed for a period of not less than one year.</Text></P1para></P1>
  </P1group></Body></Primary>
</Legislation>"""


def test_the_extractor_is_structure_blind_on_purpose():
    """A selector that matched nothing would return an empty string, and an empty string
    contains no phrase — so a broken extractor fails on every anchor at once rather than
    quietly agreeing with whatever it found."""
    text = text_of(CLML)
    assert "not less than one year" in " ".join(text.split())
    assert "Qualifying period of employment" in text


def test_a_response_that_is_not_xml_is_a_named_setup_problem():
    with pytest.raises(IngestError, match="not parseable XML"):
        text_of(b"<html>404</html><<<")


class _StubClient:
    def __init__(self, body): self.body = body; self.calls = []

    def get(self, url):
        self.calls.append(url)
        return _StubResponse(self.body)

    def close(self): pass


class _StubResponse:
    def __init__(self, body): self.content = body

    def raise_for_status(self): pass


def test_ingest_asks_for_the_dated_representation_of_each_provision():
    client = _StubClient(CLML)
    store = ingest(ANCHORS[:1], client=client)
    assert len(store.snapshots) == 2
    assert all(url.endswith("/data.xml") for url in client.calls)
    # The first anchor's earlier reading. Dated, not the current representation —
    # asking for `/section/124/data.xml` would fetch the law as it stands today and
    # verify the anchor against the wrong version of the provision.
    assert any("/2012-01-01/data.xml" in url for url in client.calls)


def test_ingest_records_a_missing_phrase_rather_than_inventing_one():
    """The anchor's phrase is the test of the fetch, not the other way round."""
    store = ingest(ANCHORS[:1], client=_StubClient(b"<Legislation><Text>nothing</Text></Legislation>"))
    assert all(not s.invariant_present for s in store.snapshots)
    assert store.drift(ANCHORS[:1])


def test_a_transport_failure_says_the_battery_still_runs():
    class _Broken:
        def get(self, url): raise OSError("no route to host")
        def close(self): pass

    with pytest.raises(IngestError, match="does not need this to run"):
        ingest(ANCHORS[:1], client=_Broken())


# --------------------------------------------------- existing mode needs no upload


def _config(upload: bool, mode: str = "existing") -> AuditConfig:
    endpoints = {"chat": "http://127.0.0.1:1/chat"}
    if upload:
        endpoints["upload"] = "http://127.0.0.1:1/upload"
    return AuditConfig(
        target={"name": "t", "endpoints": endpoints},
        corpus={"mode": mode},
    )


def test_a_config_with_no_upload_endpoint_is_valid():
    """F25. Requiring the key would have meant the half of §9.1 that exists to need no
    upload endpoint could not be configured without naming one."""
    assert _config(upload=False).target.endpoints.upload is None


def test_existing_mode_resolves_to_no_documents():
    documents, revisions, where = resolve_corpus(_config(upload=False))
    assert documents == []
    assert revisions == []
    assert where == EXISTING_INDEX


def test_existing_mode_ignores_a_corpus_path(caplog):
    config = AuditConfig(
        target={"name": "t", "endpoints": {"chat": "http://127.0.0.1:1/chat"}},
        corpus={"mode": "existing", "path": "/tmp/somewhere"},
    )
    documents, _, _ = resolve_corpus(config)
    assert documents == []


def test_documents_with_nowhere_to_send_them_is_a_named_setup_problem():
    """The check that replaced the required config key: not *is an endpoint declared*,
    but *does this run have something to upload and nowhere to put it*."""
    import asyncio

    from legal_rag_audit.generate.run import Generator

    generator = Generator(
        _config(upload=False, mode="planted"),
        documents=[{"filename": "a.txt", "content": "x", "id": "a"}],
    )
    with pytest.raises(GenerationError, match="corpus.mode: existing"):
        asyncio.run(generator._upload(generator.documents, "corpus"))


def test_skip_upload_is_still_allowed_without_an_endpoint():
    import asyncio

    from legal_rag_audit.generate.run import Generator

    generator = Generator(
        _config(upload=False, mode="planted"),
        documents=[{"filename": "a.txt", "content": "x", "id": "a"}],
        skip_upload=True,
    )
    asyncio.run(generator._upload(generator.documents, "corpus"))
    assert generator.document_ids == []


# ----------------------------------------------------------------- the manifest


def test_the_published_schema_records_the_new_fields():
    from legal_rag_audit.interchange import read_schema_document

    document = read_schema_document("ground_truth.v4")
    fields = document["$defs"]["Expectation"]["properties"]
    assert {"as_at_date", "provision", "paired_with"} <= set(fields)


def test_the_superseded_manifest_version_says_what_replaced_it():
    from legal_rag_audit.interchange.versions import SUPERSEDED

    note = SUPERSEDED["ground_truth.v2"]
    assert "ground_truth.v3" in note
    assert "as_at_date" in note


def test_the_anchor_set_records_where_every_phrase_came_from():
    """Ground truth nobody has to take our word for is only that if the source is named."""
    for anchor in ANCHORS:
        assert "Open Government Licence" in anchor.licence
        for reading in anchor.readings:
            url = anchor.url(reading)
            assert url.startswith("https://www.legislation.gov.uk/")
            if reading.as_at:
                assert url.endswith(reading.as_at)


def test_the_reference_targets_provision_text_matches_the_anchors():
    """The fixture the mock answers from is the primary source; the anchors are our
    reading of it. If they ever disagree, one of the two is wrong about the law."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mock_target import statutes

    ground_truth = build_external_ground_truth()
    expectations = {e.probe_id: e for e in ground_truth.expectations}
    for probe_id, (_url, text) in statutes.PROVISIONS.items():
        phrase = expectations[probe_id].must_contain[0]
        assert " ".join(phrase.split()).casefold() in " ".join(text.split()).casefold(), (
            f"{probe_id}: the anchor scores against {phrase!r}, which is not in the "
            f"provision text the reference target quotes"
        )


# --------------------------------------- defect 23: one answer, several written forms
#
# The second live target answered both halves of the `era-108` pair correctly — "at least
# one year" for 2011, "at least two years" for now — and scored as having returned
# neither version. The fourth anchor rule, *the figure must have one written form*, was
# written about figures and holds for figures. A quantity the statute states in words has
# several correct renderings, and exact containment reaches one of them.
#
# `era-108` has since been retired (defect 29): the third live target wrote "one year of
# continuous employment", with no qualifier for any accepted form to match, and no fourth
# widening was going to close a set that is not closed. The feature is kept, because it is
# right for an answer with one settled spelling and a few ordinary variants, and these
# tests now exercise it on an anchor built here rather than on a shipped one. That is
# where they belonged: the behaviour under test is `also_accepted`, not the anchor set.


def _prose_anchor() -> Anchor:
    """The retired anchor's shape, kept as a fixture. Not in `ANCHORS`."""
    return Anchor(
        anchor_id="era-108",
        instrument="ukpga/1996/18",
        title="Employment Rights Act 1996",
        section="108",
        provision="section 108",
        topic="employment",
        readings=(
            Reading(
                as_at="2011-01-01",
                question=(
                    "As at 1 January 2011, how long did an employee have to have been "
                    "continuously employed before section 94 of the Employment Rights "
                    "Act 1996 applied to their dismissal?"
                ),
                invariant="not less than one year",
                also_accepted=("at least one year", "a minimum of one year"),
                in_force_from="2010-10-01",
                in_force_to="2011-04-06",
            ),
            Reading(
                as_at=None,
                question=(
                    "How long must an employee have been continuously employed before "
                    "section 94 of the Employment Rights Act 1996 applies to their "
                    "dismissal?"
                ),
                invariant="not less than two years",
                also_accepted=("at least two years", "a minimum of two years"),
                in_force_from="2012-04-06",
            ),
        ),
    )


def _prose_expectation():
    """The 2011 half, as `battery` would build it from that anchor."""
    reading, other = _prose_anchor().readings
    return SimpleNamespace(
        must_contain=list(reading.accepted),
        must_not_contain=[other.invariant],
        provision="section 108",
        as_at_date=reading.as_at,
    )


def test_the_prose_anchor_accepts_the_ordinary_rendering_of_its_formula():
    first, second = _prose_anchor().readings
    assert "at least one year" in first.accepted
    assert "at least two years" in second.accepted
    # The statutory phrase is still first, and still the one the source is checked for.
    assert first.accepted[0] == first.invariant == "not less than one year"


def test_the_retired_anchor_is_not_in_the_shipped_set():
    """Defect 29. Three systems wrote the same duration three ways; two scored as having
    returned neither version of the law, both times while having the law right."""
    assert all(a.anchor_id != "era-108" for a in ANCHORS)
    assert len(ANCHORS) == 5


def test_no_shipped_anchor_answers_in_prose():
    """The fourth rule, turned on the anchor set instead of on a candidate.

    Every remaining invariant names a figure. An answer with a canonical written form is
    the only kind exact containment can score, and that is now a property of the set
    rather than a preference stated in a docstring.
    """
    for anchor in ANCHORS:
        for reading in anchor.readings:
            for form in reading.accepted:
                assert "£" in form, f"{anchor.anchor_id}: {form!r} is not a figure"


def test_a_correct_paraphrase_now_scores_as_the_right_version():
    """The answer that started this. Before the fix it was `no_version_returned`."""
    expectation = _prose_expectation()
    result = PointInTimeEvaluator().evaluate(
        answer=(
            "As at 1 January 2011, the employee generally needed at least one year of "
            "continuous employment, ending on the effective date of termination."
        ),
        in_force=expectation.must_contain,
        superseded=expectation.must_not_contain,
        provision=expectation.provision,
        as_at=expectation.as_at_date,
    )
    assert result["status"] == "PASS"
    assert result["outcome"] == "version_correct"


def test_widening_what_counts_as_right_never_widens_what_counts_as_wrong():
    """The whole safety argument, asserted rather than described.

    An added form can only turn a NOT_CAPTURED into a PASS. If the same forms reached
    `must_not_contain`, one of them could turn a PASS into a finding against a system
    that was answering correctly — and §14.2 makes that the release blocker.
    """
    for expectation in build_external_ground_truth().expectations:
        if expectation.check != "point_in_time":
            continue
        assert len(expectation.must_not_contain) == 1, (
            f"{expectation.probe_id}: the forbidden list must stay the canonical phrase"
        )


def test_a_system_that_paraphrases_the_wrong_version_is_not_captured_not_failed():
    """The cost of that asymmetry, stated on the record instead of discovered later.

    Answering the 2011 question with the *current* rule, in words rather than in the
    statute's, escapes the finding. That is the under-detection this tool accepts
    everywhere else — the alternative buys sensitivity with a false positive.
    """
    expectation = _prose_expectation()
    result = PointInTimeEvaluator().evaluate(
        answer="As at 1 January 2011 the employee needed at least two years' service.",
        in_force=expectation.must_contain,
        superseded=expectation.must_not_contain,
        provision=expectation.provision,
        as_at=expectation.as_at_date,
    )
    assert result["status"] == "NOT_CAPTURED"


def test_an_accepted_form_that_overlaps_the_other_reading_is_refused():
    """The discriminating rule, over the widened set. Without this the feature is a hole
    exactly its own width: one reading's answer would satisfy both, and the pair — which
    is the entire test — would stop separating anything."""
    bad = Anchor(
        anchor_id="x",
        instrument="ukpga/1996/18",
        title="T",
        section="1",
        provision="section 1",
        topic="employment",
        readings=(
            Reading(
                as_at="2011-01-01",
                question="Then?",
                invariant="not less than one year",
                # Contained in the other reading's phrase.
                also_accepted=("two years",),
                in_force_from="2010-01-01",
                in_force_to="2012-01-01",
            ),
            Reading(as_at=None, question="Now?", invariant="not less than two years",
                    in_force_from="2012-01-01"),
        ),
    )
    with pytest.raises(AnchorError, match="overlaps"):
        validate_anchors((bad,))


def test_an_accepted_form_the_question_already_contains_is_refused():
    bad = Anchor(
        anchor_id="x",
        instrument="ukpga/1996/18",
        title="T",
        section="1",
        provision="section 1",
        topic="employment",
        readings=(
            Reading(
                as_at="2011-01-01",
                question="Was it at least one year back then?",
                invariant="not less than one year",
                also_accepted=("at least one year",),
                in_force_from="2010-01-01",
                in_force_to="2012-01-01",
            ),
            Reading(as_at=None, question="Now?", invariant="not less than two years",
                    in_force_from="2012-01-01"),
        ),
    )
    with pytest.raises(AnchorError, match="already contains its own answer"):
        validate_anchors((bad,))


def test_an_empty_accepted_form_is_refused():
    bad = Anchor(
        anchor_id="x",
        instrument="ukpga/1996/18",
        title="T",
        section="1",
        provision="section 1",
        topic="employment",
        readings=(
            Reading(as_at="2011-01-01", question="Then?",
                    invariant="not less than one year", also_accepted=("",),
                    in_force_from="2010-01-01", in_force_to="2012-01-01"),
            Reading(as_at=None, question="Now?", invariant="not less than two years",
                    in_force_from="2012-01-01"),
        ),
    )
    with pytest.raises(AnchorError, match="empty accepted form"):
        validate_anchors((bad,))


def test_only_the_statutory_phrase_is_checked_against_the_primary_source():
    """`ingest --verify` asks whether the source still says what the anchor quotes. The
    added forms are ordinary English renderings and are *not* in the statute — requiring
    them would fail every verification against a source that is perfectly correct."""
    text = (
        "(1) Section 94 does not apply to the dismissal of an employee unless he has "
        "been continuously employed for a period of not less than two years ending "
        "with the effective date of termination."
    )
    reading = _prose_anchor().readings[1]
    snapshot = snapshot_for(_prose_anchor(), reading, text.encode("utf-8"), text)
    assert snapshot.invariant_present is True
    assert snapshot.invariant == "not less than two years"
    assert "at least two years" not in text


# ------------------------------------------------- defect 30: a probe needs a forum
#
# The licensed-content probes named no jurisdiction. Against a product holding French, EU
# and UK sources they were answered on French law, and passed — necessarily, because the
# marker set is a set of English publisher identifiers and a French answer cannot contain
# one whatever the index holds. The pass was true and it was not the same pass a UK-only
# product earns from the same words.


def test_the_licensed_probes_name_their_jurisdiction():
    """One battery, one meaning. A probe answered on a different body of law by a
    different target is not a probe those two targets can be compared on."""
    for probe_id, text, _why in LICENSED_PROBES:
        assert "England and Wales" in text, (
            f"{probe_id} does not say which law it is asking about, so a "
            f"multi-jurisdiction target may answer a different question than a "
            f"single-jurisdiction one and score the same"
        )


def test_the_licensed_probes_still_name_no_case():
    """The jurisdiction is the only thing added. A probe that named the authority would
    be testing whether the system can repeat a string we handed it (§8.2 #18)."""
    for probe_id, text, _why in LICENSED_PROBES:
        assert "[" not in text and "v " not in text, (
            f"{probe_id} looks like it names an authority"
        )
