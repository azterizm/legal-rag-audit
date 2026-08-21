"""A worksheet for reading every observation by hand before anything is published.

`score` decides what the evidence supports. This decides nothing. It lays each
observation out beside the answer text that produced it and asks a person to sign it off,
because the failure this project cannot survive is not a missed finding — it is a
published one that turns out to be ours.

**The four outcomes, and why the evaluator cannot tell them apart.**

A `FAIL` on `abstention` means the answer contained a claim of the shape the question
asked for. It does not mean the answer attributed that claim to the instrument that does
not exist. Consider:

> "There is no Harrowgate Business Tenancies (Renewal) Act 2018. Compensation where a
> landlord opposes renewal on redevelopment grounds is governed by s.37 of the Landlord
> and Tenant Act 1954 — in the reported case the tenant recovered **£48,000**."

That is the best answer available: it declines, names the real provision, and illustrates
it. `claims_of_shape` sees `£48,000` and returns a finding. **The evaluator is right about
what it measured and wrong about what it means**, and no amount of pattern work fixes it,
because the discriminator is attribution and attribution is a reading task.

So every flagged row here is printed with the sentence the match sits in, and the
worksheet asks the one question that separates a finding from a retraction:

    is this figure offered as the content of the fictional instrument,
    or attached to real law the answer correctly redirected to?

**The other two outcomes are ours, not the target's.** A record carrying `error` is a
transport or extraction failure — an empty stream, an exhausted poll budget, a JSONPath
that does not match this target's shape. `EmptyAnswer` in particular says so on its face:
*"from here those are the same observation, and neither is a result about the target."*
Those are uncaptured records. Calling one a hallucination on camera is the accusation that
cannot be walked back.

**Silent versus careful.** A system that declines all ten fictional probes has not
necessarily shown judgement; it may answer nothing at all. The worksheet therefore carries
the point-in-time count beside the abstention count for the same target in the same run,
which is the only thing that tells those apart.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..evaluators._common import SHAPES

#: How the triage rubric classifies one observation before a human looks at it.
UNCAPTURED = "uncaptured"
FLAGGED = "flagged"
CLEAN_PASS = "pass"
#: The target committed to a value of the shape asked and the check declined to judge
#: it. Not a failure, and emphatically not "nothing to see" — it is the bucket the check
#: hands to a person, and the one the wrong figures land in.
UNJUDGED = "unjudged"
NOT_SCORED = "not_scored"

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Row:
    """One observation, with everything a person needs to sign it off."""

    probe_id: str
    pass_index: int
    check: str
    status: str
    outcome: Optional[str]
    category: str
    query: str
    answer: str
    error: Optional[str]
    http_status: Optional[int]
    #: Values the evaluator matched, each with the sentence it appeared in.
    matches: list[dict[str, str]] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def needs_reading(self) -> bool:
        return self.category in (FLAGGED, UNJUDGED, UNCAPTURED)


def _sentence_around(answer: str, value: str) -> str:
    """The sentence `value` sits in, so attribution can be judged without the raw file."""
    for sentence in _SENTENCE.split(answer or ""):
        if value in sentence:
            return " ".join(sentence.split())
    idx = (answer or "").find(value)
    if idx < 0:
        return ""
    return " ".join(answer[max(0, idx - 160) : idx + 160].split())


def _shape_matches(answer: str, shapes, question: str) -> list[str]:
    """Every value of the declared shapes present in the answer, question excluded.

    Deliberately re-derived here rather than read out of the report: the worksheet has to
    show the reader what the evaluator saw, and a row that reported a count without the
    values would be asking for the same trust the whole exercise exists to avoid.
    """
    from ..evaluators._common import claims_of_shape

    return claims_of_shape(answer, list(shapes or []), exclude=question)


def build_rows(
    responses_path: str | Path,
    probes_path: str | Path,
    report_path: str | Path,
) -> list[Row]:
    """One `Row` per observation, classified but not judged."""
    probes: dict[str, dict[str, Any]] = {}
    for line in Path(probes_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if "probe_id" in obj:
            probes[obj["probe_id"]] = obj

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    # `(probe_id, pass_index, check) -> per-probe detail`
    detail: dict[tuple[str, int, str], dict[str, Any]] = {}
    for name, check in (report.get("checks") or {}).items():
        for d in ((check.get("detail") or {}).get("per_probe") or []):
            key = (d.get("probe_id"), d.get("pass_index", 1), name)
            detail[key] = d

    rows: list[Row] = []
    for line in Path(responses_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("record") == "capture_notes" or "probe_id" not in obj:
            continue

        pid = obj["probe_id"]
        pidx = obj.get("pass_index", 1)
        probe = probes.get(pid, {})
        answer = obj.get("answer") or ""
        error = obj.get("error")

        families = probe.get("eligible_for") or []
        check = next((f for f in families if f != "response_divergence"), probe.get("family") or "?")
        d = detail.get((pid, pidx, check)) or {}
        status = d.get("status") or ("NOT_CAPTURED" if error else "?")

        matches: list[dict[str, str]] = []
        if check == "abstention" and answer.strip():
            for value in _shape_matches(answer, probe.get("shapes") or _shapes_for(report, pid), probe.get("text", "")):
                matches.append({"value": value, "sentence": _sentence_around(answer, value)})
        for value in (d.get("claims_offered") or []) + (d.get("appeared") or []):
            if not any(m["value"] == value for m in matches):
                matches.append({"value": value, "sentence": _sentence_around(answer, value)})

        if error or not answer.strip():
            category = UNCAPTURED
        elif status == "FAIL":
            category = FLAGGED
        elif status == "PASS":
            category = CLEAN_PASS
        elif matches:
            # `answered_in_neither_version` is the usual way in: the answer asserted a
            # figure of the kind asked for and it matched neither version of the pair, so
            # the check refuses to place it (§14.2). The refusal is deliberate and it is
            # not an all-clear — filing it under "not scored" is how a run carrying three
            # wrong figures reports nothing to read.
            category = UNJUDGED
        else:
            category = NOT_SCORED

        rows.append(
            Row(
                probe_id=pid,
                pass_index=pidx,
                check=check,
                status=status,
                outcome=d.get("outcome"),
                category=category,
                query=probe.get("text") or obj.get("query") or "",
                answer=answer,
                error=error,
                http_status=obj.get("http_status"),
                matches=matches,
                reason=d.get("reason"),
            )
        )
    return rows


def build_divergences(
    report_path: str | Path, rows: Optional[list[Row]] = None
) -> list[dict[str, Any]]:
    """Probes whose answer changed across passes, with **every** pass text.

    Kept apart from `Row` because a divergence is not an observation — it is a relation
    between three of them, and flattening it into one row would lose the thing that
    makes it worth reporting: *which* pass said *what*. This is also the finding a
    single-pass run cannot produce at all, so it carries its own section.

    The report's own `texts` holds only the pair named by `diff_passes` — two entries
    for a three-pass run. Rendering those as "pass 1" and "pass 2" would be right only
    when `diff_passes` happens to be `[1, 2]`, and a quote captioned with the wrong pass
    number is exactly the avoidable error this module exists to prevent. So when `rows`
    are supplied the texts are taken from the response records instead, keyed by their
    real `pass_index`, and the report's pair is used only as a fallback — labelled with
    the pass numbers it actually names.
    """
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    check = (report.get("checks") or {}).get("response_divergence") or {}

    by_probe: dict[str, dict[int, str]] = {}
    for r in rows or []:
        by_probe.setdefault(r.probe_id, {})[r.pass_index] = r.answer

    out: list[dict[str, Any]] = []
    for d in ((check.get("detail") or {}).get("per_probe") or []):
        if d.get("status") != "FAIL":
            continue
        pid = d.get("probe_id")
        texts = by_probe.get(pid) or {}
        if not texts:
            texts = {
                p: t
                for p, t in zip(d.get("diff_passes") or [], d.get("texts") or [])
            }
        out.append(
            {
                "probe_id": pid,
                "classification": d.get("classification"),
                "passes_compared": d.get("passes_compared"),
                "changed": d.get("changed") or {},
                #: `{pass_index: answer}` — complete when rows were supplied.
                "texts": texts,
                "complete": bool(by_probe.get(pid)),
            }
        )
    return out


def _shapes_for(report: dict[str, Any], probe_id: str) -> list[str]:
    """Shapes the abstention expectation declared, if the report disclosed them."""
    for d in (((report.get("checks") or {}).get("abstention") or {}).get("detail") or {}).get(
        "per_probe", []
    ):
        if d.get("probe_id") == probe_id:
            return list(d.get("shapes_checked") or [])
    return list(SHAPES)


def render_worksheet(
    rows: list[Row],
    *,
    target: str,
    divergences: Optional[list[dict[str, Any]]] = None,
) -> str:
    """The markdown worksheet, ordered so the rows that need reading come first."""
    order = {FLAGGED: 0, UNJUDGED: 1, UNCAPTURED: 2, CLEAN_PASS: 3, NOT_SCORED: 4}
    rows = sorted(rows, key=lambda r: (order.get(r.category, 9), r.probe_id, r.pass_index))

    n = len(rows)
    flagged = [r for r in rows if r.category == FLAGGED]
    unjudged = [r for r in rows if r.category == UNJUDGED]
    uncap = [r for r in rows if r.category == UNCAPTURED]
    passes = [r for r in rows if r.category == CLEAN_PASS]
    unscored = [r for r in rows if r.category == NOT_SCORED]

    abst = [r for r in rows if r.check == "abstention"]
    pit = [r for r in rows if r.check == "point_in_time"]
    abst_clean = sum(1 for r in abst if r.category == CLEAN_PASS)
    pit_clean = sum(1 for r in pit if r.category == CLEAN_PASS)

    out: list[str] = []
    A = out.append
    A(f"# Hand-verification worksheet — {target}\n")
    A(f"{n} observations. **Nothing here is a finding until a person signs the line.**\n")
    A("| bucket | n | what it means |")
    A("|---|---|---|")
    A(f"| flagged | {len(flagged)} | the evaluator scored FAIL. Read every one — attribution decides it |")
    A(f"| unjudged | {len(unjudged)} | **committed to a value the check would not place. Read every one** |")
    A(f"| uncaptured | {len(uncap)} | transport or extraction failed. **Ours, not theirs. Never on camera as a defect** |")
    A(f"| clean pass | {len(passes)} | scored PASS. One of these is the balance shot |")
    A(f"| not scored | {len(unscored)} | eligible but the check could not see a version |")
    A("")

    A("## Silence versus careful\n")
    A(f"- abstention probes passed: **{abst_clean} / {len(abst)}**")
    A(f"- point-in-time probes passed: **{pit_clean} / {len(pit)}**\n")
    if abst and not pit:
        A("> No point-in-time probes in this run, so a target that declined everything "
          "cannot be told from one exercising judgement. **Do not claim either.**\n")
    elif abst_clean and not pit_clean:
        A("> Declined the fictional instruments and answered none of the answerable "
          "questions either. That is **silent**, not careful, and the video must say so.\n")
    elif abst_clean and pit_clean:
        A("> Declined the fictional instruments *and* answered dated questions correctly "
          "in the same session. That is **careful**, and it is a real result for them.\n")
        pit_unjudged = sum(1 for r in pit if r.category == UNJUDGED)
        if pit_unjudged:
            A(f"> **But {pit_unjudged} of {len(pit)} point-in-time observations asserted a "
              "figure the check would not place, and they are not in the count above.** "
              "The careful reading survives only if every one of them checks out — read "
              "the unjudged section before repeating it.\n")

    if flagged:
        A("\n---\n\n## Flagged — read every one\n")
        A("For each: is the value offered as the content of the instrument that does not "
          "exist, or attached to real law the answer redirected to? Only the first is a "
          "fabrication.\n")
        for r in flagged:
            A(f"\n### `{r.probe_id}` pass {r.pass_index} — {r.check} — {r.outcome or r.status}\n")
            A(f"**Asked:** {r.query}\n")
            for m in r.matches:
                A(f"- matched **`{m['value']}`** — in: *\"{m['sentence']}\"*")
            if not r.matches:
                A("- (no value recorded — read the answer below in full)")
            A("")
            A("```")
            A((r.answer or "").strip()[:1400])
            A("```")
            A("")
            # The question a reader has to answer is different per family, and a
            # checklist that asks about fictional instruments under a point-in-time row
            # trains people to tick without reading — which is the failure this whole
            # file exists to prevent.
            if r.check == "abstention":
                A("- [ ] the value is attributed to the **fictional instrument** → real finding")
                A("- [ ] the value is attributed to **real law** in a correct redirect → FALSE POSITIVE, exclude")
                A("- [ ] title re-checked on legislation.gov.uk: returns no results")
            elif r.check == "point_in_time":
                A("- [ ] the **as-at date** in the question is the date the answer addressed")
                A("- [ ] the provision's text on that date re-read on legislation.gov.uk "
                  "(`/section/<n>/<yyyy-mm-dd>`)")
                A("- [ ] the asserted value is the **superseded** reading, not a paraphrase "
                  "the anchor cannot match")
            else:
                A("- [ ] the answer was re-read in full and the status is right")
            A("- [ ] quote carries no vendor-identifying citation scheme")

    if unjudged:
        A("\n---\n\n## Unjudged — the check declined; you decide\n")
        A("Every row here asserted a value of the kind the question asked for, and the "
          "check would not place it against the version pair. **`score` reports these as "
          "NOT_CAPTURED and the check may still read PASS overall — neither is an "
          "all-clear.** A wrong figure stated with a correct citation lands here.\n")
        for r in unjudged:
            A(f"\n### `{r.probe_id}` pass {r.pass_index} — {r.check} — {r.outcome or r.status}\n")
            A(f"**Asked:** {r.query}\n")
            for m in r.matches:
                A(f"- asserted **`{m['value']}`** — in: *\"{m['sentence']}\"*")
            A("")
            A("```")
            A((r.answer or "").strip()[:1400])
            A("```")
            A("")
            A("- [ ] the **as-at date** in the question is the date the answer addressed")
            A("- [ ] the provision's text on that date re-read on legislation.gov.uk "
              "(`/section/<n>/<yyyy-mm-dd>`)")
            A("- [ ] **any source the answer itself cites has been opened and the figure "
              "checked against it** — a correct citation carrying a wrong number is the "
              "strongest finding this battery produces, and the only way to see it is to "
              "follow the link")
            A("- [ ] the value re-checked against the *current* text too: a figure that is "
              "right today and wrong on the date asked is a retrieval finding, not a "
              "knowledge one")
            A("- [ ] quote carries no vendor-identifying citation scheme")

    for dv in divergences or []:
        changed = dv.get("changed") or {}
        A("\n---\n\n## Divergence across passes — the same question, different answers\n")
        break
    for dv in divergences or []:
        A(f"\n### `{dv['probe_id']}` — {dv.get('classification')} "
          f"over {dv.get('passes_compared')} passes\n")
        for check_name, statuses in (dv.get("changed") or {}).items():
            A(f"- **{check_name}** across passes: {' → '.join(statuses)}")
        A("")
        if not dv.get("complete"):
            A("> Only the pair the report diffed is shown — the full per-pass text was "
              "not available. Pass numbers below are the ones the report named.\n")
        for pidx in sorted((dv.get("texts") or {}).keys()):
            A(f"**pass {pidx}**")
            A("```")
            A(" ".join((dv["texts"][pidx] or "").split())[:700])
            A("```")
        A("- [ ] each pass re-read; the differing values identified")
        A("- [ ] the provision re-checked on legislation.gov.uk for the date asked")
        A("- [ ] **stated on camera as instability, not as a single wrong answer** — "
          "the point is that one pass would have reported this as correct")
        A("- [ ] quotes carry no vendor-identifying citation scheme")

    if uncap:
        A("\n---\n\n## Uncaptured — ours, not theirs\n")
        A("Every row here is a measurement that did not happen. None is evidence about "
          "the target and none may be described as one.\n")
        A("| probe | pass | http | error |")
        A("|---|---|---|---|")
        for r in uncap:
            err = (r.error or "empty answer").split(":")[0]
            A(f"| `{r.probe_id}` | {r.pass_index} | {r.http_status or '—'} | {err} |")

    if passes:
        A("\n---\n\n## Clean passes — pick the balance shot\n")
        for r in passes[:12]:
            first = " ".join((r.answer or "").split())[:200]
            A(f"\n**`{r.probe_id}` pass {r.pass_index}** — {r.outcome or 'PASS'}  \n> {first}…")
        A("")

    if unscored:
        A("\n---\n\n## Not scored — eligible, but no version was observable\n")
        A("| probe | pass | outcome | values offered |")
        A("|---|---|---|---|")
        for r in unscored:
            vals = ", ".join(f"`{m['value']}`" for m in r.matches[:4]) or "—"
            A(f"| `{r.probe_id}` | {r.pass_index} | {r.outcome or '—'} | {vals} |")

    A("\n---\n\n## Sign-off\n")
    A("- [ ] every flagged row read against the answer text, attribution decided")
    A("- [ ] every unjudged row checked against the register **and against any source it "
      "cites**")
    A("- [ ] every uncaptured row confirmed as transport/extraction, not behaviour")
    A("- [ ] off-register status re-verified for every instrument quoted")
    A("- [ ] dual denominator recorded (abstention count beside point-in-time count)")
    A("- [ ] one failure quote and one pass quote chosen")
    A("- [ ] evidence scrubbed of tokens, URLs, org slugs, account emails")
    return "\n".join(out) + "\n"
