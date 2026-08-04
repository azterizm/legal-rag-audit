"""What `validate` puts on the terminal.

Separate from the run so the same observation can be asserted against in a test without
the test reading prose, and so the ordering decision below is in one place.

**The raw body comes before our reading of it.** §7.1 asks for the raw response body
*alongside* what each JSONPath extracted, and which of the two is printed first is not
cosmetic. Printed second, the body reads as supporting material for a conclusion we
already stated. Printed first, the conclusion is checkable against something the reader
saw with their own eyes — which is the same argument the evidence bundle makes for
Tier 1 findings, at a much smaller scale.

Candidate paths are printed under a heading that says they are guesses. A suggestion
that reads as an instruction is how an operator ends up scoring a request id as an
answer.
"""

from typing import Optional

from .run import Validation
from .suggest import answer_candidates, citation_candidates

RULE = "─" * 68


def _duration(seconds: float) -> str:
    # "0 seconds" is what a localhost stub honestly produces and is still a sentence
    # nobody should read in a projection, so the floor is named rather than rounded to.
    if seconds < 60:
        return "under a minute"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"


def _quote(text: str, prefix: str = "    │ ") -> list[str]:
    return [prefix + line for line in (text or "(empty)").splitlines()] or [
        prefix + "(empty)"
    ]


def render(result: Validation) -> str:
    lines: list[str] = ["", RULE]
    lines.append(f"  validate — {result.target_name}")
    lines.append(RULE)
    lines.append("")
    lines.append(
        "  Three neutral queries. Nothing from the battery was asked, nothing was "
        "scored,"
    )
    lines.append("  and nothing was written to disk.")
    lines.append("")
    lines.append(f"  answer path         {result.answer_field}")
    lines.append(f"  citations path      {result.citations_field}")
    transports = {o.transport for o in result.observations}
    lines.append(f"  transport           {', '.join(sorted(transports)) or 'none'}")
    lines.append("")

    lines.extend(_upload_section(result))
    if result.retrieval is not None:
        lines.append(f"  retrieval endpoint  {result.retrieval}")
        lines.append("")

    for obs in result.observations:
        lines.append(RULE)
        lines.append(f"  {obs.probe_id}   {obs.query}")
        indent = " " * (len(obs.probe_id) + 5)
        lines.append(f"  {' ' * len(obs.probe_id)}   {_wrap(obs.purpose, 62, indent)}")
        lines.append("")
        status = obs.http_status if obs.http_status is not None else "no response"
        lines.append(
            f"    {obs.method} {obs.url} → {status} in {obs.elapsed_ms} ms"
        )
        if obs.receive_url:
            lines.append(f"    listening on {obs.receive_url}")
        if obs.frames:
            # A poll is not a stream, and reusing the stream's vocabulary for it would
            # describe an answer arriving as "the target's terminator".
            if obs.transport == "poll":
                unit, ended = "polls", {
                    "terminator": "the answer arrived",
                    "deadline": "the answer never arrived",
                }
            else:
                unit, ended = "frames", {
                    "terminator": "ended by the target's terminator",
                    "connection close": "ended when the target closed the connection",
                    "deadline": "ended by our deadline, not by the target",
                }
            lines.append(
                f"    {obs.frames} {unit}, "
                f"{ended.get(obs.ended_by, 'still open')}"
            )
        if obs.error:
            lines.append(f"    error: {obs.error}")
        lines.append("")

        lines.append("    Raw response:")
        lines.extend(_quote(obs.raw))
        if obs.truncated:
            lines.append("    │ … truncated for display")
        lines.append("")

        lines.append("    Extracted by the configured paths:")
        if obs.extracted:
            lines.append(f"      answer     {_one_line(obs.answer)}")
        else:
            lines.append("      answer     nothing — the path matched no value")
        if obs.citations:
            lines.append(
                f"      citations  {len(obs.citations)} items: "
                f"{_one_line(str(obs.citations))}"
            )
        else:
            lines.append("      citations  nothing")
        lines.append("")

        lines.extend(_candidates(obs))

    lines.extend(_projection(result))
    lines.extend(_diagnoses(result))
    return "\n".join(lines).rstrip() + "\n"


def _one_line(value: Optional[str], width: int = 180) -> str:
    flat = " ".join((value or "").split())
    return flat if len(flat) <= width else flat[:width] + "…"


def _candidates(obs) -> list[str]:
    """Only when something did not extract. A guess beside a working config is noise."""
    if obs.parsed is None:
        return []
    wanted_answer = not obs.extracted
    wanted_citations = not obs.citations
    if not (wanted_answer or wanted_citations):
        return []

    answers = answer_candidates(obs.parsed) if wanted_answer else []
    citations = citation_candidates(obs.parsed) if wanted_citations else []
    if not answers and not citations:
        return []

    lines = [
        "    Candidate paths — guesses from the shape of the body, not answers.",
        "    Read the value beside each one before setting it.",
        "",
    ]
    for candidate in answers:
        lines.append(f"      answer_field:     {candidate.path}")
        lines.append(f"                        {candidate.why}")
        lines.append(f"                        {candidate.sample}")
    for candidate in citations:
        lines.append(f"      citations_field:  {candidate.path}")
        lines.append(f"                        {candidate.why} — {candidate.sample}")
    lines.append("")
    return lines


def _upload_section(result: Validation) -> list[str]:
    upload = result.upload
    if upload is None:
        return []
    if not upload.attempted:
        return [f"  upload              not attempted — {upload.skipped_because}", ""]
    if upload.error:
        return [f"  upload              failed — {upload.error}", ""]
    if upload.identifier:
        return [
            f"  upload              accepted, id {upload.identifier!r} "
            f"(delete `{_document_name()}` when you are done)",
            "",
        ]
    return [
        "  upload              accepted, but no identifier came back",
        "",
    ]


def _document_name() -> str:
    from .neutral import NEUTRAL_DOCUMENT_FILENAME

    return NEUTRAL_DOCUMENT_FILENAME


def _projection(result: Validation) -> list[str]:
    lines = [RULE, ""]
    if result.median_ms is None:
        lines.append(
            "  No query returned 200, so there is no latency to project a run from."
        )
        lines.append("")
        return lines
    seconds = result.projected_seconds or 0
    passes = f"{result.passes} {'pass' if result.passes == 1 else 'passes'}"
    lines.append(
        f"  median {result.median_ms} ms per query × {result.probe_count} probes × "
        f"{passes}"
    )
    lead = "" if seconds < 60 else "≈ "
    lines.append(
        f"  {lead}{_duration(seconds)} for the battery, asked one at a time "
        f"({result.probe_count_source})."
    )
    lines.append("")
    return lines


def _diagnoses(result: Validation) -> list[str]:
    if not result.diagnoses:
        return [
            RULE,
            "",
            "  Nothing to report. Every neutral query returned an answer the "
            "configured",
            "  paths could read.",
            "",
            "  This says the harness can talk to the target. It says nothing about "
            "the target.",
            "",
        ]

    blocking = [d for d in result.diagnoses if d.blocking]
    advisory = [d for d in result.diagnoses if not d.blocking]

    lines = [RULE, ""]
    lines.append(
        f"  {len(result.diagnoses)} "
        f"{'problem' if len(result.diagnoses) == 1 else 'problems'}: "
        f"{len(blocking)} would stop the run, {len(advisory)} would not."
    )
    lines.append("")

    for diagnosis in blocking + advisory:
        mark = "STOP  " if diagnosis.blocking else "NOTE  "
        where = f"  [{diagnosis.probe_id}]" if diagnosis.probe_id else ""
        lines.append(f"  {mark}{diagnosis.title}{where}")
        lines.append(f"        code            {diagnosis.code}")
        lines.append(f"        saw             {_wrap(diagnosis.saw)}")
        lines.append(f"        would look like {_wrap(diagnosis.mistaken_for)}")
        lines.append(f"        do              {_wrap(diagnosis.remedy)}")
        lines.append("")

    if blocking:
        lines.append(
            "  Exit 2 — did not run. These are setup problems, not findings about "
            "the target."
        )
        lines.append("")
    return lines


def _wrap(text: str, width: int = 70, indent: str = " " * 24) -> str:
    import textwrap

    wrapped = textwrap.wrap(" ".join(text.split()), width=width)
    if not wrapped:
        return ""
    return ("\n" + indent).join(wrapped)
