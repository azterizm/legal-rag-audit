"""Phase I — the boundary as a property of the software (§13, F37).

§16 tells a reader, in prose, that signing up for a product authorises use and not
testing. This file is where that stops being a promise about our conduct. The acceptance
is two sentences:

> An injection battery without authorisation aborts; the report shows who authorised what,
> when.

Both halves are here, and so are the three things that make the control worth having
rather than a box to tick:

* **It fires before anything is sent.** A gate that reported afterwards would be a log
  entry, not a control. The abort is asserted against a target that would have recorded
  any request it received.
* **It cannot be satisfied by the config alone for production.** Two acts, deliberately:
  a config is copied between runs and a command line is typed for one.
* **The free paths stay free.** `validate` and the existing-corpus battery need no
  authorisation, and that is not an oversight to be closed later — it is what makes them
  the pre-sale check and the free pre-finding. A gate that caught them would have been
  written to the wrong rule.

The classification itself is data (`authorisation.FAMILIES`), so the test that matters
most is the one asserting it covers every family either battery asks. A family nobody
classified would otherwise fall through to the fail-closed default, which is a backstop
and not a design.
"""

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from legal_rag_audit.authorisation import (
    AUTHORISED,
    BY_FAMILY,
    ORDINARY,
    PRODUCTION_ACK,
    Authorisation,
    AuthorisationError,
    authorised_testing,
    classify,
    reasons,
    require,
)
from legal_rag_audit.config import AuditConfig
from legal_rag_audit.external import build_external_probes
from legal_rag_audit.probes import build_probes
from legal_rag_audit.validate import NEUTRAL_PROBES

REPO_ROOT = Path(__file__).resolve().parents[1]

PLANTED_FAMILIES = sorted({p.family for p in build_probes()})
EXISTING_FAMILIES = sorted({p.family for p in build_external_probes()})


def _block(**overrides) -> Authorisation:
    fields = {
        "authorised_by": "A. Person, Head of Engineering",
        "authorised_on": date.today() - timedelta(days=3),
        "environment": "staging",
        "scope_ack": "injection, canary and upload probes authorised in writing",
    }
    fields.update(overrides)
    return Authorisation(**fields)


# ------------------------------------------------------------------- classification


def test_every_family_either_battery_asks_is_classified():
    """The fail-closed default is a backstop, not the design.

    An unclassified family would be treated as needing authorisation, which is the safe
    direction — and would also mean nobody had thought about it. This is what stops that
    from being how families get classified.
    """
    unclassified = [
        family
        for family in PLANTED_FAMILIES + EXISTING_FAMILIES
        if family not in BY_FAMILY
    ]
    assert not unclassified, (
        f"§13 does not class {unclassified}. Decide what running one actually does to "
        f"somebody else's system, and record it in `authorisation.FAMILIES` — the "
        f"fail-closed default exists for the gap between writing a check and deciding "
        f"its legal class, not as a place to leave one."
    )


def test_an_unknown_family_is_treated_as_needing_authorisation():
    assert classify("something-nobody-wrote-yet").requires == AUTHORISED
    assert reasons(["something-nobody-wrote-yet"])


def test_the_planted_battery_needs_authorisation():
    needed = authorised_testing(PLANTED_FAMILIES)
    names = {f.family for f in needed}
    assert {"injection_resistance", "cross_tenant_leakage", "index_freshness"} <= names


def test_the_existing_corpus_battery_needs_none():
    """§9.1's second configuration is the free pre-finding, and this is why.

    Every family on it is ordinary use and it uploads nothing, so it clears both tests
    the gate applies. If this ever fails, the half that exists to run before anybody has
    signed anything has stopped being able to.
    """
    assert authorised_testing(EXISTING_FAMILIES) == []
    assert reasons(EXISTING_FAMILIES, uploads=False) == []
    for family in EXISTING_FAMILIES:
        assert classify(family).requires == ORDINARY


def test_uploading_needs_authorisation_on_its_own():
    """Even a battery of nothing but ordinary questions, if it uploads.

    §16.1 puts *uploading adversarial documents* in the right-hand column, and the
    planted corpus carries an injection payload by construction. The act needing consent
    is the upload, independent of what is then asked.
    """
    needed = reasons(EXISTING_FAMILIES, uploads=True)
    assert len(needed) == 1
    assert needed[0].what == "uploading a corpus"
    assert "existing" in needed[0].because, (
        "the message has to name the way out — the configuration that needs no upload "
        "and no authorisation is the thing an operator most needs to be told about here"
    )


def test_every_reason_is_reported_not_just_the_first():
    """An operator who fixes one and runs into the next has been told the truth twice."""
    with pytest.raises(AuthorisationError) as excinfo:
        require(None, PLANTED_FAMILIES, uploads=True)
    message = str(excinfo.value)
    assert "uploading a corpus" in message
    assert "injection_resistance" in message
    assert "cross_tenant_leakage" in message
    # And it says what to write, not only that something is missing.
    assert "authorised_by" in message and "scope_ack" in message


def test_the_message_names_the_computer_misuse_act_where_it_applies():
    """Not decoration. The reason cross-tenant probing is different in kind from the
    rest is a statute, and an operator deciding whether to press on should read it."""
    with pytest.raises(AuthorisationError) as excinfo:
        require(None, ["cross_tenant_leakage"])
    assert "Computer Misuse Act 1990" in str(excinfo.value)


# ------------------------------------------------------------------------- the record


def test_a_block_satisfies_the_gate():
    block = _block()
    assert require(block, PLANTED_FAMILIES, uploads=True) is block


def test_an_ordinary_run_needs_no_block_and_is_not_given_one():
    assert require(None, EXISTING_FAMILIES) is None


def test_a_future_dated_authorisation_is_refused():
    """A typo or a backdating attempt, and the report would carry it either way."""
    with pytest.raises(ValidationError, match="future"):
        _block(authorised_on=date.today() + timedelta(days=1))


def test_an_empty_scope_is_refused():
    with pytest.raises(ValidationError):
        _block(scope_ack="  ")
    with pytest.raises(ValidationError):
        _block(authorised_by="")


def test_the_age_is_recorded_rather_than_gated():
    """No expiry is enforced, on purpose.

    Any number we chose would be ours presented as a standard — the `0.85` mistake F24
    exists to prevent. What a reader needs is the figure, so they can decide whether a
    scope from two years ago still covers this run.
    """
    old = _block(authorised_on=date.today() - timedelta(days=900))
    assert require(old, PLANTED_FAMILIES, uploads=True) is old
    assert old.age_days() == 900


# ------------------------------------------------------------------------- production


def test_production_needs_the_flag_as_well_as_the_config():
    block = _block(environment="production")
    with pytest.raises(AuthorisationError) as excinfo:
        require(block, EXISTING_FAMILIES)
    message = str(excinfo.value)
    assert PRODUCTION_ACK in message
    assert "no config-only path" in message


def test_production_with_the_flag_runs():
    block = _block(environment="production")
    assert require(block, PLANTED_FAMILIES, uploads=True, production_ack=True) is block


def test_the_flag_alone_does_not_authorise_anything():
    """The two controls are independent. A flag with no block is still no consent."""
    with pytest.raises(AuthorisationError, match="declares none"):
        require(None, PLANTED_FAMILIES, uploads=True, production_ack=True)


def test_the_flag_is_on_generate_and_says_what_it_is_for():
    """Long and unpleasant on purpose: the kind of thing nobody puts in a shell alias
    without noticing. And it has to be a real flag, not a constant nothing wires up."""
    import os

    assert PRODUCTION_ACK == "--i-have-written-authorisation-for-production"
    help_text = subprocess.run(
        [sys.executable, "-m", "legal_rag_audit.cli", "generate", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    ).stdout
    assert PRODUCTION_ACK in help_text
    assert "no config-only path" in help_text


# ------------------------------------------------------------------------- validate


def test_validate_needs_no_authorisation():
    """§13 rule 4, and it is what makes `validate` the free pre-sale check.

    Its probes carry no family at all — they are three neutral throwaway questions, and
    the package they live in has no import path to the battery. There is nothing here for
    the gate to classify, which is the correct answer rather than an exemption.
    """
    assert NEUTRAL_PROBES
    assert reasons([getattr(p, "family", "") for p in NEUTRAL_PROBES if getattr(p, "family", "")]) == []


# ------------------------------------------------------------------------ end to end


def _config(tmp_path: Path, *, authorisation: str = "") -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  name: nowhere\n"
        "  endpoints:\n"
        "    chat: http://127.0.0.1:1/chat\n"
        "    upload: http://127.0.0.1:1/upload\n"
        "corpus:\n"
        "  mode: planted\n" + authorisation,
        encoding="utf-8",
    )
    return path


def _run(config: Path, tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    import os

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "legal_rag_audit.cli",
            "generate",
            "-c",
            str(config),
            "-o",
            str(tmp_path / "responses.jsonl"),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )


def test_an_injection_battery_without_authorisation_aborts_before_anything_is_sent(
    tmp_path,
):
    """The acceptance, first half.

    The endpoint is port 1 on loopback — nothing is listening. So a run that got as far
    as sending would fail with a connection error and a written response file; this one
    exits 2 with a diagnosis and writes nothing, which is the difference between a
    control and a log entry.
    """
    result = _run(_config(tmp_path), tmp_path)

    assert result.returncode == 2, f"{result.stdout}\n{result.stderr}"
    assert "Traceback" not in result.stderr
    assert "injection_resistance" in result.stderr
    assert "Signing up for a product authorises use, not testing" in result.stderr
    assert not (tmp_path / "responses.jsonl").exists()
    # The corpus is planted to disk before the gate runs, and that is fine — nothing left
    # the machine. What must not exist is a record of anything having been asked.
    assert "Connection" not in result.stderr and "connect" not in result.stderr


def test_a_production_config_without_the_flag_aborts(tmp_path):
    block = (
        "authorisation:\n"
        "  authorised_by: A. Person, CTO\n"
        f"  authorised_on: '{date.today().isoformat()}'\n"
        "  environment: production\n"
        "  scope_ack: full battery authorised in writing\n"
    )
    result = _run(_config(tmp_path, authorisation=block), tmp_path)

    assert result.returncode == 2
    assert PRODUCTION_ACK in result.stderr
    assert not (tmp_path / "responses.jsonl").exists()


def test_the_config_accepts_and_validates_the_block(tmp_path):
    block = (
        "authorisation:\n"
        "  authorised_by: A. Person, CTO\n"
        f"  authorised_on: '{date.today().isoformat()}'\n"
        "  environment: staging\n"
        "  scope_ack: full battery authorised in writing\n"
        "  reference: engagement letter 2026-03\n"
    )
    config = AuditConfig.load_from_yaml(str(_config(tmp_path, authorisation=block)))
    assert config.authorisation is not None
    assert config.authorisation.environment == "staging"
    assert config.authorisation.reference == "engagement letter 2026-03"


def test_a_config_with_no_block_loads():
    """Optional in the schema, required by the run. A required key would be filled in
    with whatever made the error go away; a run that aborts naming the families it would
    have asked is a decision somebody has to make."""
    config = AuditConfig(
        **{
            "target": {"name": "t", "endpoints": {"chat": "http://x/chat"}},
            "corpus": {"mode": "existing"},
        }
    )
    assert config.authorisation is None


# ------------------------------------------------------------------- in the report


def test_the_report_shows_who_authorised_what_and_when(tmp_path):
    """The acceptance, second half — §13 rule 3, verbatim.

    Built from the interchange records rather than from a live run: what is under test is
    that the block survives the journey from config to response file to manifest to
    attestation, and a target would add nothing to that.
    """
    from legal_rag_audit.interchange import (
        CaptureNotes,
        Response,
        write_ground_truth,
        write_probes,
        write_responses,
    )
    from legal_rag_audit.probes import build_ground_truth
    from legal_rag_audit.score import score
    from legal_rag_audit.score.attestation import render

    probes = build_probes()
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "gt.json", build_ground_truth())

    block = _block(reference="engagement letter 2026-03, clause 4")
    write_responses(
        tmp_path / "r.jsonl",
        [
            Response(run_id="r", probe_id=p.probe_id, query=p.text, answer="An answer.")
            for p in probes
        ],
        capture_notes=CaptureNotes(
            record="capture_notes",
            citations_captured=False,
            retrieved_chunks_captured=False,
            authorisation=block,
        ),
    )

    report = score(
        str(tmp_path / "r.jsonl"),
        str(tmp_path / "gt.json"),
        str(tmp_path / "probes.jsonl"),
        skip_tier2=True,
    )

    recorded = report["manifest"]["authorisation"]
    assert recorded["authorised_by"] == block.authorised_by
    assert recorded["authorised_on"] == block.authorised_on.isoformat()
    assert recorded["environment"] == "staging"
    assert recorded["scope_ack"] == block.scope_ack
    assert recorded["reference"] == "engagement letter 2026-03, clause 4"
    assert "authorisation" not in report["manifest"]["not_recorded"]

    page = render(report, probes)
    assert "### Authorisation" in page
    assert block.authorised_by in page
    assert block.authorised_on.isoformat() in page
    assert "not itself evidence that the declaration was true" in page, (
        "the page must not let a typed name imply more than it establishes"
    )


def test_a_battery_that_needed_authorisation_and_has_none_says_so_in_the_limits(
    tmp_path,
):
    """The artefact route case (§5.1.1), and it must not read as a clean run.

    A response file from the target's own harness against their own system legitimately
    carries no block. Scoring it is right; printing nothing about the gap is not. An
    absent record of consent and a recorded one must never read the same (F40).
    """
    from legal_rag_audit.interchange import Response, write_ground_truth, write_probes
    from legal_rag_audit.interchange import write_responses
    from legal_rag_audit.probes import build_ground_truth
    from legal_rag_audit.score import score
    from legal_rag_audit.score.attestation import render

    probes = build_probes()
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "gt.json", build_ground_truth())
    write_responses(
        tmp_path / "r.jsonl",
        [
            Response(run_id="r", probe_id=p.probe_id, query=p.text, answer="An answer.")
            for p in probes
        ],
    )

    report = score(
        str(tmp_path / "r.jsonl"),
        str(tmp_path / "gt.json"),
        str(tmp_path / "probes.jsonl"),
        skip_tier2=True,
    )

    assert report["manifest"]["authorisation"] is None
    gap = report["manifest"]["not_recorded"]["authorisation"]
    assert "injection_resistance" in gap
    assert "cannot say who authorised" in gap

    page = render(report, probes)
    assert "### Authorisation" not in page, (
        "an empty section would suggest a block was reproduced and was blank"
    )
    assert gap in page, "the gap belongs where a reader looks for what a run does not show"


def test_an_ordinary_run_records_that_none_was_needed(tmp_path):
    """Different from the one above, and the report must not print them the same.

    *No authorisation, and none needed* and *no authorisation, and one was needed* are
    opposite facts about a run.
    """
    from legal_rag_audit.external import build_external_ground_truth
    from legal_rag_audit.interchange import Response, write_ground_truth, write_probes
    from legal_rag_audit.interchange import write_responses
    from legal_rag_audit.score import score

    probes = build_external_probes()
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "gt.json", build_external_ground_truth())
    write_responses(
        tmp_path / "r.jsonl",
        [
            Response(run_id="r", probe_id=p.probe_id, query=p.text, answer="An answer.")
            for p in probes
        ],
    )

    report = score(
        str(tmp_path / "r.jsonl"),
        str(tmp_path / "gt.json"),
        str(tmp_path / "probes.jsonl"),
        skip_tier2=True,
    )

    gap = report["manifest"]["not_recorded"]["authorisation"]
    assert "none was needed" in gap
    assert "ordinary use" in gap


def test_the_manifest_schema_carries_the_block():
    from legal_rag_audit.interchange import read_schema_document

    document = read_schema_document("run_manifest.v1")
    assert "authorisation" in document["properties"]

    responses = read_schema_document("responses.v3")
    notes = next(
        variant
        for variant in responses["oneOf"]
        if "capture_notes" in json.dumps(variant)
    )
    assert "authorisation" in json.dumps(notes)
