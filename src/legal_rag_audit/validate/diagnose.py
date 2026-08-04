"""Named setup problems, and what each one would have looked like without this (NF9).

§7.1's argument is that setup problems and findings are different kinds of thing, and
that a harness which cannot tell them apart will eventually publish the first as the
second. The table in that section is a list of conditions beside *what each one looks
like in a report if nobody caught it* — that second column is the reason the mode
exists, so it is carried here rather than paraphrased into a log line.

Every diagnosis names four things:

* what we saw — the observation, not our interpretation of it;
* what it would have been scored as — the false finding this prevents;
* what to change — a config key, not a suggestion to investigate;
* whether it stops the run. Some do not: an upload endpoint with no identifier is a
  real loss of one Tier 1 check and a perfectly runnable engagement.

`blocking` is what the exit code reads. A non-blocking diagnosis is still printed in
full, because *"this will run, and this check will be missing from the report"* is
something the operator has to know before the run rather than after it.
"""

from dataclasses import dataclass
from typing import Optional

#: Exit 2 — "did not run". `validate` never returns 1: it makes no judgement about any
#: answer, so it has no findings, and returning the findings code would put a setup
#: check and an audit result in the same bucket for whatever CI reads it.
BLOCKING = True
ADVISORY = False


@dataclass(frozen=True)
class Diagnosis:
    code: str
    title: str
    #: The observation. Written so it could be pasted into a bug report against their
    #: system without us in the loop.
    saw: str
    #: §7.1's second column: what this becomes in a report if it goes uncaught.
    mistaken_for: str
    #: The change, named concretely — a config key, an env var, an endpoint.
    remedy: str
    blocking: bool = BLOCKING
    probe_id: Optional[str] = None


def auth_rejected(status: int, probe_id: str, token_env: Optional[str]) -> Diagnosis:
    where = (
        f"`auth.token_env: {token_env}` — check the variable is exported in this shell"
        if token_env
        else "`auth` is set to `none` in the config; if the target needs a credential, "
        "set `auth.type` and `auth.token_env`"
    )
    return Diagnosis(
        code="auth_rejected",
        title=f"The target refused the request: HTTP {status}",
        saw=f"{status} on a neutral query. No answer was returned.",
        mistaken_for=(
            "an empty answer. Half the battery reads an empty answer as the system "
            "failing to produce something it should have — so a wrong token becomes "
            "a page of hallucination and abstention findings about a system that "
            "never saw a single question."
        ),
        remedy=where,
        probe_id=probe_id,
    )


def rate_limited(status: int, probe_id: str, retry_after: Optional[str]) -> Diagnosis:
    wait = f" It asked us to wait {retry_after}s." if retry_after else ""
    return Diagnosis(
        code="rate_limited",
        title=f"The target rate-limited three neutral queries: HTTP {status}",
        saw=f"{status} within the first three requests.{wait}",
        mistaken_for=(
            "non-determinism. Some probes answer and some do not, the same probe "
            "answers on one pass and not the next, and the variance pass reports a "
            "system whose behaviour changes between identical questions (§8.3). It "
            "does not — ours does."
        ),
        remedy=(
            "raise the limit for the run window, or agree a rate with the target and "
            "reduce `battery.passes`. Three queries is the floor; the battery is "
            "considerably more than three."
        ),
        probe_id=probe_id,
    )


def stream_never_terminated(
    probe_id: str, seconds: float, frames: int, configured: Optional[str]
) -> Diagnosis:
    how = (
        f"`response_format.stop_payload_match: {configured!r}` never appeared in any "
        f"frame"
        if configured
        else "no `stop_payload_match` and no `stop_field` is configured, so there is "
        "nothing that tells us the answer is complete"
    )
    return Diagnosis(
        code="stream_never_terminated",
        title="The stream never said it was finished",
        saw=(
            f"{frames} frames in {seconds:.0f}s and then our own deadline, not the "
            f"target's terminator. {how}."
        ),
        mistaken_for=(
            "a timeout scored as a failure — or worse, a truncated answer scored as "
            "a complete one. An answer cut off mid-sentence is missing whatever it "
            "was about to say, and every check that reads for a token that should be "
            "present would record its absence as a finding."
        ),
        remedy=(
            "set `response_format.stop_payload_match` to a string that appears only "
            "in the final frame, or `stop_field`/`stop_value` for a structured "
            "terminator. The frames above are printed so you can pick one."
        ),
        probe_id=probe_id,
    )


def answer_never_arrived(probe_id: str, seconds: float, polls: int) -> Diagnosis:
    return Diagnosis(
        code="answer_never_arrived",
        title="The answer never appeared on the receive endpoint",
        saw=(
            f"the query was accepted, then {polls} polls over {seconds:.0f}s and the "
            f"configured answer path never matched anything that came back."
        ),
        mistaken_for=(
            "every probe empty, and from there a system that declines to answer its "
            "own documentation. A decoupled endpoint that is slower than we wait is "
            "not the same as one that says nothing."
        ),
        remedy=(
            "raise `--timeout` if the target is simply slow — and if it is this slow, "
            "read the run-length projection below before starting. If the answer "
            "arrives somewhere other than `endpoints.receive`, that is the key to "
            "change."
        ),
        probe_id=probe_id,
    )


def handshake_failed(probe_id: str, url: str, detail: str) -> Diagnosis:
    return Diagnosis(
        code="handshake_failed",
        title="The websocket connected but produced nothing",
        saw=f"{detail} ({url}).",
        mistaken_for=(
            "a total run failure with no diagnosis: every probe empty, every check "
            "reading it as the system declining to answer. The handshake is the "
            "least visible part of the config and the most likely to be wrong."
        ),
        remedy=(
            "`endpoints.receive.init_message` is the subscription frame the target "
            "expects before it will send anything. Compare what is configured with "
            "what their own client sends on connect."
        ),
        probe_id=probe_id,
    )


def upload_no_identifier(returned: str) -> Diagnosis:
    return Diagnosis(
        code="upload_no_identifier",
        title="The upload endpoint returned no document identifier",
        saw=f"The upload succeeded and the body carried no usable `id`: {returned}",
        mistaken_for=(
            "nothing at all, which is the problem. Citation integrity tests whether "
            "a cited document id is in the set the target issued at upload (§8.2 #2). "
            "With no identifiers there is no set, the check is NOT_CAPTURED, and the "
            "report is quietly one Tier 1 check shorter than it looks."
        ),
        remedy=(
            "if the target does return an id under another key, there is no config "
            "for that yet — say so and we will add it. If it genuinely issues none, "
            "the run is still worth doing and citation integrity will be reported as "
            "not captured rather than passed (F40)."
        ),
        blocking=ADVISORY,
    )


def answer_not_extracted(
    probe_id: str, path: str, body_was_json: bool, candidates: list[str]
) -> Diagnosis:
    if not body_was_json:
        saw = (
            "the response body is not JSON, so no JSONPath can match it. The raw "
            "body is printed above."
        )
        remedy = (
            "if the target returns plain text, there is no config for that yet — say "
            "so. If this is an error page, the status line above is the thing to read."
        )
    elif candidates:
        saw = f"`{path}` matched nothing in the response body."
        remedy = (
            "set `response_format.answer_field` to the path the answer is actually "
            "at. Guessed from the body, in order of likelihood: "
            + ", ".join(f"`{c}`" for c in candidates)
        )
    else:
        saw = f"`{path}` matched nothing in the response body."
        remedy = (
            "set `response_format.answer_field` to the path the answer is actually "
            "at. Nothing in the body looked like an answer, so there is no candidate "
            "to offer — the body is printed above."
        )
    return Diagnosis(
        code="answer_not_extracted",
        title="The configured answer path extracted nothing",
        saw=saw,
        mistaken_for=(
            "a hallucination, or an abstention, or a system that returns nothing — "
            "this is the leading cause of false positives in this method (§7.1), and "
            "a false positive in a delivered report is not recoverable."
        ),
        remedy=remedy,
        probe_id=probe_id,
    )


def citations_not_extracted(path: str, candidates: list[str]) -> Diagnosis:
    if candidates:
        remedy = (
            "set `response_format.citations_field`. Candidate lists in the body: "
            + ", ".join(f"`{c}`" for c in candidates)
        )
    else:
        remedy = (
            "if the target returns no citations at all, leave this: the report will "
            "record the citation checks as not captured rather than passed (F40)."
        )
    return Diagnosis(
        code="citations_not_extracted",
        title="The configured citations path extracted nothing",
        saw=f"`{path}` matched no list in any of the three responses.",
        mistaken_for=(
            "a system that cites nothing. It may well be — but the report should say "
            "citations were not captured, not that none were made, and it cannot tell "
            "those apart from here."
        ),
        remedy=remedy,
        blocking=ADVISORY,
    )


def unreachable(probe_id: str, url: str, error: str) -> Diagnosis:
    return Diagnosis(
        code="unreachable",
        title="The request never completed",
        saw=f"{error} ({url}).",
        mistaken_for=(
            "every probe recorded as a transport error. Scoring reads those as "
            "NOT_CAPTURED and reports nothing about the system, which is correct and "
            "also a wasted engagement."
        ),
        remedy=(
            "check the URL, the network path from this machine, and whether the "
            "target expects a client certificate or an allowlisted source address."
        ),
        probe_id=probe_id,
    )


def bad_status(status: int, probe_id: str) -> Diagnosis:
    return Diagnosis(
        code="bad_status",
        title=f"The target returned HTTP {status} to a neutral query",
        saw=f"{status}. The body is printed above.",
        mistaken_for=(
            "an empty answer, and from there a finding about a system that returned "
            "an error to a question about itself."
        ),
        remedy=(
            "the body above usually names the cause — a missing field in "
            "`endpoints.chat.body`, an unsupported method, a wrong path."
        ),
        probe_id=probe_id,
    )


def run_too_long(median_ms: int, probes: int, passes: int, hours: float) -> Diagnosis:
    return Diagnosis(
        code="run_too_long",
        title=f"At this latency the battery takes about {hours:.1f} hours",
        saw=(
            f"median {median_ms} ms per query over three neutral queries × "
            f"{probes} probes × {passes} "
            f"{'pass' if passes == 1 else 'passes'}, run one at a time."
        ),
        mistaken_for=(
            "nothing, until hour three. It is not a defect in anything — it is a fact "
            "about the engagement that is much cheaper to know now."
        ),
        remedy=(
            "agree the window with the target before starting, or reduce "
            "`battery.passes` — at one pass reproducibility is not measured and the "
            "report says so (§8.3), which is a real cost and a defensible trade."
        ),
        blocking=ADVISORY,
    )
