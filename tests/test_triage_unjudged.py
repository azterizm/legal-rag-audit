"""The bucket a run with three wrong figures must not be silent about.

`point_in_time` refuses to score an answer whose figure matches neither version of the
pair (§14.2). That refusal is deliberate, and it is also where the strongest findings in
the battery live: a figure that is right today and wrong on the date asked, or a figure
stated under a correct citation to an instrument that does not contain it. Filing those
rows under "not scored" let a worksheet report `need reading 0` on exactly such a run.
"""

import json
from pathlib import Path

import pytest

from legal_rag_audit.score.triage import (
    CLEAN_PASS,
    NOT_SCORED,
    UNJUDGED,
    build_rows,
    render_worksheet,
)

HEADER = {"schema": "responses.v3", "record": "capture_notes"}


def probe(pid, family="point_in_time", text="As at 1 June 2014, what was the cap?"):
    return {
        "schema": "probes.v2",
        "probe_id": pid,
        "family": family,
        "intent": "positive",
        "text": text,
        "eligible_for": [family, "response_divergence"],
    }


def response(pid, answer, pass_index=1):
    return {
        "schema": "responses.v3",
        "run_id": "run-a",
        "probe_id": pid,
        "pass_index": pass_index,
        "query": "As at 1 June 2014, what was the cap?",
        "answer": answer,
        "error": None,
    }


def report(per_probe, status="PASS", abstention=()):
    return {
        "schema": "report.v1",
        "checks": {
            "point_in_time": {
                "check": "point_in_time",
                "tier": 1,
                "status": status,
                "eligible": len(per_probe),
                "scored": 0,
                "failed": 0,
                "detail": {"per_probe": per_probe},
            },
            "abstention": {
                "check": "abstention",
                "tier": 1,
                "status": "PASS" if abstention else "NOT_ELIGIBLE",
                "eligible": len(abstention),
                "scored": len(abstention),
                "failed": 0,
                "detail": {"per_probe": list(abstention)},
            },
        },
    }


def write(path, records):
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


@pytest.fixture
def bench(tmp_path):
    def build(per_probe, responses, probes=None, status="PASS", abstention=()):
        pfile = write(tmp_path / "probes.jsonl", probes or [probe("pit-1")])
        rfile = write(tmp_path / "responses.jsonl", [HEADER, *responses])
        report_path = tmp_path / "report.json"
        report_path.write_text(
            json.dumps(report(per_probe, status, abstention)), encoding="utf-8"
        )
        return build_rows(rfile, pfile, report_path)

    return build


NEITHER = {
    "probe_id": "pit-1",
    "pass_index": 1,
    "status": "NOT_CAPTURED",
    "outcome": "answered_in_neither_version",
    "claims_offered": ["£751"],
}

DECLINED = {
    "probe_id": "pit-1",
    "pass_index": 1,
    "status": "NOT_CAPTURED",
    "outcome": "declined_to_state_a_version",
    "claims_offered": [],
}


def test_a_figure_the_check_would_not_place_needs_reading(bench):
    rows = bench([NEITHER], [response("pit-1", "The cap was £751 on that date.")])
    assert rows[0].category == UNJUDGED
    assert rows[0].needs_reading


def test_declining_to_state_a_figure_does_not_need_reading(bench):
    """Saying nothing is the safe behaviour; it is not a row to hand a person."""
    rows = bench([DECLINED], [response("pit-1", "I could not produce a grounded answer.")])
    assert rows[0].category == NOT_SCORED
    assert not rows[0].needs_reading


def test_the_asserted_value_is_carried_with_its_sentence(bench):
    rows = bench([NEITHER], [response("pit-1", "Something else. The cap was £751 then.")])
    assert rows[0].matches[0]["value"] == "£751"
    assert "£751" in rows[0].matches[0]["sentence"]


def test_a_scored_pass_is_never_unjudged(bench):
    passing = dict(NEITHER, status="PASS", outcome="version_correct", claims_offered=["£464"])
    rows = bench([passing], [response("pit-1", "The cap was £464.")])
    assert rows[0].category == CLEAN_PASS


def test_the_worksheet_prints_the_row_and_says_pass_is_not_an_all_clear(bench):
    rows = bench([NEITHER], [response("pit-1", "The cap was £751 on that date.")])
    md = render_worksheet(rows, target="t")
    assert "## Unjudged" in md
    assert "£751" in md
    assert "all-clear" in md
    assert "| unjudged | 1 |" in md


def test_the_worksheet_tells_the_reader_to_open_the_answers_own_citation(bench):
    """A correct citation carrying a wrong number is only visible if you follow the link."""
    rows = bench([NEITHER], [response("pit-1", "Per SI 2013/1949 the cap was £75,000.")])
    md = render_worksheet(rows, target="t")
    assert "cites has been opened" in md


def test_the_careful_verdict_is_qualified_when_figures_went_unjudged(bench):
    """`13/13 abstention, 1/10 point-in-time` must not read as an unqualified pass."""
    probes = [probe("pit-1"), probe("pit-2"), probe("fict-1", family="abstention")]
    per = [
        NEITHER,
        dict(NEITHER, probe_id="pit-2", status="PASS", outcome="version_correct", claims_offered=["£464"]),
    ]
    rows = bench(
        per,
        [
            response("pit-1", "The cap was £751 on that date."),
            response("pit-2", "The cap was £464."),
            response("fict-1", "No such Act exists."),
        ],
        probes=probes,
        abstention=[{"probe_id": "fict-1", "pass_index": 1, "status": "PASS"}],
    )
    md = render_worksheet(rows, target="t")
    assert "That is **careful**" in md
    assert "not in the count above" in md


def test_need_reading_is_not_zero_on_a_run_carrying_wrong_figures(bench):
    """The regression this file exists for."""
    rows = bench([NEITHER], [response("pit-1", "The cap was £751 on that date.")])
    assert sum(1 for r in rows if r.needs_reading) == 1
