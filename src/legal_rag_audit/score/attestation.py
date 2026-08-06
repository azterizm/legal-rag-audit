"""The Markdown attestation (§10.6, F30). The JSON is evidence; this is testimony.

Order is load-bearing (§10.1): manifest, Tier 1, Tier 2, limits. Deal-enders first,
and the provenance before either, because a reader deciding whether to believe the
findings needs to know what produced them before they read one.

Three register rules, enforced by construction rather than by care:

* **Counts, never a headline rate** (§3.5, Appendix D). Every number on this page
  comes with the denominator it was measured against, and there is no single figure
  anywhere that could be quoted without one.
* **Measured vs By design** (§10.2). Tier 1 sections are labelled *Measured*. This
  writer emits no remediation and no mechanism claims — §10.4's mechanism section is
  written by a person from the findings, because naming a cause requires visibility
  into a stack the tool does not have. The document says that in place of guessing.
* **Tier 2 states its instrument** (§4.1) and its distribution (F24), because a line
  we configured is not a standard anyone published.

Sections 5 and 6 of the §10.6 skeleton — the representation delta and the mechanisms
— are deliberately left as marked placeholders. Both require material the tool cannot
see: their published claims, and an architectural reading. Generating either would be
the failure this project exists to measure in other people's systems.
"""

from typing import Any

from ..interchange import Probe
from .distributions import render as render_distribution

PASS = "PASS"
FAIL = "FAIL"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
NOT_CAPTURED = "NOT_CAPTURED"

_KEY_MEANING = {
    "open": "published with the battery",
    "held": "sealed until this report",
    "conditional": "resolved by whether retrieved chunks were captured",
}


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else f"{noun}s"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    return [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
        *["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows],
        "",
    ]


def render(
    report: dict[str, Any],
    probes: list[Probe],
    target_name: str = "the target system",
) -> str:
    """The attestation, as Markdown."""
    manifest = report["manifest"]
    checks = report["checks"]
    summary = report["summary"]
    capture = report["capture"]
    by_probe = {p.probe_id: p for p in probes}

    lines: list[str] = []
    add = lines.append

    add(f"# Retrieval Integrity Diagnostic — {target_name}")
    add("")
    add(
        f"Run started {manifest['run']['started']} · "
        f"scored by legal-rag-audit {manifest['tool']['version']}"
    )
    add("")

    # ---------------------------------------------------------------- 0. What this is
    add("## 0. What this document is")
    add("")
    add(
        f"An evaluation of {target_name} against a fixed battery of "
        f"{manifest['battery']['total_probes']} probes, fired "
        f"{manifest['run']['passes']} "
        f"{_plural(manifest['run']['passes'], 'time')} each."
    )
    add("")
    add(
        "**Tier 1** findings are exact matches against ground truth authored before "
        "the run. No model is involved in scoring them, so they are contestable on "
        "the facts and on nothing else. **Tier 2** findings are scored by a named "
        "instrument at a stated line, and are contestable on both — the instrument "
        "and the line are printed with every one."
    )
    add("")
    add(
        f"Of {summary['checks_registered']} registered checks, "
        f"{summary['passed']} passed, {summary['failed']} produced findings, "
        f"{summary['not_eligible']} did not apply to this deployment, and "
        f"{summary['not_captured']} could not run on what the response file carried. "
        f"**The last two are not passes** and are listed in full in §8."
    )
    add("")

    # ------------------------------------------------------------------- 1. Manifest
    add("## 1. Run manifest")
    add("")
    lines.extend(_manifest_table(manifest))
    lines.extend(_pre_commitment(manifest))

    # --------------------------------------------------------------- 2. Tier 1
    add("## 2. Tier 1 findings — Measured")
    add("")
    tier1 = [checks[name] for name in report["tier1"] if checks[name]["status"] == FAIL]
    if not tier1:
        add("No Tier 1 check produced a finding on this run.")
        add("")
    else:
        for check in tier1:
            lines.extend(_check_section(check, by_probe, report))

    # Measurements sit inside §2 and outside the findings table. A number with no
    # threshold cannot fail, and any threshold we invented for one would be ours rather
    # than a standard (§8.2 #15). Their interpretation belongs in §6, written by a person.
    for name in report["summary"].get("measurements", []):
        measurement = checks.get(name)
        if measurement and measurement["status"] not in (NOT_ELIGIBLE, NOT_CAPTURED):
            lines.extend(_measurement_section(measurement))

    # --------------------------------------------------------------- 3. Tier 2
    add("## 3. Tier 2 metrics — Measured, instrument disclosed")
    add("")
    tier2 = [checks[name] for name in report["tier2"]]
    scored_tier2 = [c for c in tier2 if c.get("distribution")]
    if not scored_tier2:
        add(
            "No Tier 2 check produced a distribution on this run. The reasons are in "
            "§6."
        )
        add("")
    for check in scored_tier2:
        lines.extend(_tier2_section(check))

    # ---------------------------------------------------------- 4. Reproducibility
    add("## 4. Reproducibility")
    add("")
    add(
        f"Scoring is deterministic: the same response file produces byte-identical "
        f"findings, digest `{manifest['scoring']['findings_hash']}`. "
        f"**That is a property of this instrument, not of {target_name}** — running "
        f"the battery twice against a non-deterministic target legitimately produces "
        f"different findings, and the difference would itself be a result."
    )
    add("")
    lines.extend(_variance_section(report, checks, target_name))

    # ------------------------------------------------- 5. Delta and 6. Mechanisms
    add("## 5. Representation delta")
    add("")
    add(
        "*Not generated.* This section sets the target's own published claims against "
        "what was observed, and every claim in it must be quoted verbatim with a URL "
        "and a retrieval date. The tool has no access to those, and a paraphrase of "
        "marketing copy is an argument where a dated quotation is a measurement."
    )
    add("")

    add("## 6. Mechanisms — By design")
    add("")
    add(
        "*Not generated.* Naming the design property behind a finding — *citations "
        "are emitted by the generation step rather than the retrieval layer, so "
        "citation validity is probabilistic by construction* — requires visibility "
        "into an architecture this diagnostic does not have. Exactly three belong "
        "here, written by a person from the findings above, with the cause named and "
        "no remediation attached."
    )
    add("")

    # --------------------------------------------------- 7. Reproduce, 8. Limits
    add("## 7. How to reproduce this report")
    add("")
    lines.extend(_reproduction(manifest))

    add("## 8. Limits — what this run does not establish")
    add("")
    for limit in _limits(report, capture):
        add(f"- {limit}")
    add("")
    add("### What did not run")
    add("")
    lines.extend(_not_run(report))

    return "\n".join(lines).rstrip() + "\n"


def _manifest_table(manifest: dict[str, Any]) -> list[str]:
    tool = manifest["tool"]
    inputs = manifest["inputs"]
    run = manifest["run"]
    rows = [
        ["Tool version", f"`{tool['version']}`"],
        ["Commit", f"`{tool['commit_sha']}`" if tool["commit_sha"] else "—"],
        [
            "Commit signature",
            (
                f"{tool['commit_signature']} — verify with "
                f"`{tool['commit_signature_verify_with']}`"
                if tool.get("commit_signature_verify_with")
                else str(tool["commit_signature"] or "—")
            ),
        ],
        ["Working tree", tool["working_tree"] or "—"],
        ["Planted tree", f"`{inputs['corpus_hash']}`" if inputs["corpus_hash"] else "—"],
        ["Probe file", f"`{inputs['query_set_hash']}`" if inputs["query_set_hash"] else "—"],
        ["Ground truth", f"`{inputs['ground_truth_manifest_hash']}`"],
        ["Responses", f"`{inputs['responses_hash']}`"],
        ["Findings digest", f"`{manifest['scoring']['findings_hash']}`"],
        ["Passes", manifest["run"]["passes"]],
        [
            "Questions put verbatim",
            f"{manifest['capture'].get('probes_asked_verbatim', 0)} of "
            f"{manifest['capture']['records']} records",
        ],
        ["Corpus mode", run.get("corpus_mode") or "—"],
        [
            "Corpus",
            (
                f"{run['corpus']} — `{run.get('corpus_digest') or '—'}`"
                if run.get("corpus")
                else "—"
            ),
        ],
        # Both halves. A seed on its own says the battery was reproducible; only the
        # source says whether it was also unguessable, and those are different claims.
        [
            "Seed",
            (
                f"`{run['seed']}` — {run.get('seed_source') or 'source not recorded'}"
                if run.get("seed")
                else "—"
            ),
        ],
        ["Plants", run.get("plants", 0)],
        ["Remote scoring", "false — enforced, not asserted"],
    ]

    # §13 rule 3 — verbatim, so the artefact carries its own provenance of consent. Its
    # own block rather than a manifest row, because a reader deciding whether this run
    # should have happened is asking a different question from the one the hashes answer.
    out = _table(["Field", "Value"], rows)
    out.extend(_authorisation(manifest))

    gaps = manifest.get("not_recorded") or {}
    if gaps:
        out.append("Not recorded on this run, and why:")
        out.append("")
        out.extend(
            _table(
                ["Field", "Why"],
                [[f"`{field}`", reason] for field, reason in sorted(gaps.items())],
            )
        )
    return out


def _authorisation(manifest: dict[str, Any]) -> list[str]:
    """Who authorised what, on what date, in which environment."""
    block = manifest.get("authorisation")
    if not block:
        # Silence here would read as *no authorisation was needed*, which is sometimes
        # true and sometimes the opposite. `not_recorded` says which, and the manifest
        # table above already prints it — so this section only appears when there is a
        # consent to reproduce.
        return []

    rows = [
        ["Authorised by", block.get("authorised_by") or "—"],
        ["Authorised on", block.get("authorised_on") or "—"],
        ["Environment", block.get("environment") or "—"],
        ["Scope acknowledged", block.get("scope_ack") or "—"],
    ]
    if block.get("reference"):
        rows.append(["Reference", block["reference"]])

    out = ["", "### Authorisation", ""]
    out.extend(_table(["Field", "Value"], rows))
    out.append(
        "Reproduced verbatim from the response file. It records what the operator "
        "declared; it is not itself evidence that the declaration was true, and a "
        "reader who needs that should ask for the written authorisation it references."
    )
    out.append("")
    return out


def _pre_commitment(manifest: dict[str, Any]) -> list[str]:
    pre = manifest["pre_commitment"]
    out = ["### Pre-commitment", ""]
    if pre["status"] != "verified":
        out.append(
            "No handover record was supplied, so **this run makes no pre-commitment "
            "claim.** The ground truth is disclosed alongside this report, but "
            "nothing here establishes that it was fixed before the responses were "
            "collected."
        )
        out.append("")
        return out

    out.append(
        f"The digests below were published at handover on **{pre['created']}**, "
        f"before any response existed. They were recomputed at scoring time and "
        f"matched: {', '.join(f'`{name}`' for name in pre['verified'])}. A mismatch "
        f"would have aborted the run rather than produced this document."
    )
    out.append("")
    if pre["carried"]:
        out.append(
            f"Carried from the handover record without recomputation: "
            f"{', '.join(f'`{name}`' for name in pre['carried'])} — scoring reads no "
            f"corpus, so its digest can only be the one committed to earlier."
        )
        out.append("")
    out.append(
        "The ground-truth manifest is included with this report as "
        "`ground_truth.json`. It hashes to the value above; the sealed half of the "
        "battery is now disclosed in full."
    )
    out.append("")
    return out


def _pass_split_line(check: dict[str, Any], report: dict[str, Any]) -> list[str]:
    """§3.5 rule 4 — the split between a stable defect and a flaky one.

    *"60 eligible probes × 3 passes = 180 observations. Never collapse them."* Printed
    only above one pass. At `passes: 1` every failure trivially failed all of its one
    pass, and a `0 failed on some passes only` beside a single pass reads as *no
    non-determinism was found* when in fact none could have been.
    """
    passes = (report.get("summary", {}).get("variance") or {}).get("passes", 1)
    if passes < 2 or check.get("cross_cutting"):
        return []

    stable = check.get("failed_all_passes", 0)
    flaky = check.get("failed_some_passes", 0)
    if not (stable or flaky):
        return []

    line = (
        f"Across {passes} passes: **{stable} {_plural(stable, 'probe')} failed on every "
        f"pass** (a defect that reproduces), **{flaky} on some passes only** "
        f"(non-deterministic)."
    )
    if flaky:
        line += (
            " The second group is the one that will not reproduce when this battery is "
            "re-run, and is reported separately for that reason rather than folded into "
            "the count above."
        )
    return [line, ""]


def _check_section(
    check: dict[str, Any], by_probe: dict[str, Probe], report: dict[str, Any]
) -> list[str]:
    out = [f"### `{check['check']}` — {check['failed']} of {check['scored']} scored", ""]
    out.append(f"**Recipe:** {check['recipe']}")
    out.append("")
    out.append(
        f"**Expectation was {check['key']}** "
        f"({_KEY_MEANING.get(check['key'], check['key'])})."
    )
    out.append("")
    out.append(
        f"{check['failed']} of {check['scored']} scored "
        f"{_plural(check['scored'], 'record')} failed, against {check['eligible']} "
        f"{_plural(check['eligible'], 'probe')} declared eligible before the run."
    )
    out.append("")
    out.extend(_pass_split_line(check, report))
    if check.get("limit"):
        # In the same artefact as the finding, never in a later post (§3.3, Source Map
        # §7.5). §8.2 makes this mandatory for injection; the field carries it for every
        # check that has one, so the report cannot print the finding without the sentence.
        out.append(f"> [!IMPORTANT]")
        out.append(f"> **What this does not establish.** {check['limit']}.")
        out.append("")
    if check.get("partial"):
        out.append(f"**Partial:** {check['partial']}")
        out.append("")
    out.extend(_unscoreable(check))

    instances = report.get("evidence", {}).get(check["check"])
    if instances:
        out.append(
            f"Verbatim evidence for every instance is in "
            f"`{instances['file']}` — {instances['instances']} "
            f"{'instance' if instances['instances'] == 1 else 'instances'}."
        )
        out.append("")

    rows = []
    for record in check.get("detail", {}).get("per_probe", []):
        if record.get("status") != FAIL:
            continue
        probe = by_probe.get(record.get("probe_id"))
        rows.append(
            [
                f"`{record.get('probe_id')}`",
                record.get("pass_index", "—"),
                (probe.text[:70] + "…") if probe and len(probe.text) > 70
                else (probe.text if probe else "—"),
            ]
        )
    out.extend(_table(["Probe", "Pass", "Asked"], rows))
    return out


def _variance_section(
    report: dict[str, Any], checks: dict[str, Any], target_name: str
) -> list[str]:
    """Inter-pass divergence (§8.3, F22), inside §4 where reproducibility is argued.

    The section a report needs most the second time it is read. A vendor who re-runs the
    battery and gets different numbers will conclude the tool is unreliable — unless the
    document said, before they tried, that their system was the thing that varied and by
    how much.
    """
    summary = report["summary"].get("variance") or {}
    if not summary:
        return []

    passes = summary.get("passes", 1)
    check = checks.get("response_divergence", {})
    out: list[str] = []

    if passes < 2:
        out.append(
            "**This run asked each probe once, so nothing was compared.** Inter-pass "
            "divergence is `NOT_CAPTURED`, not a pass: a single-pass run is not "
            "evidence that the answers are reproducible, and no count below should be "
            "read as one. Re-run with `--passes 3`."
        )
        out.append("")
        return out

    out.append(
        f"Each probe was asked **{passes} times**. Classification is on Tier 1 outcomes "
        f"only — {len(summary.get('invariant_checks', []))} checks — because a Tier 2 "
        f"score crossing a threshold between passes crosses a line we set, and that "
        f"would be our setting reported as {target_name}'s non-determinism."
    )
    out.append("")
    out.extend(
        _table(
            ["Classification", "Probes", "What it means"],
            [
                [
                    "`identical`",
                    str(summary.get("identical", 0)),
                    "byte-equal answers after whitespace normalisation",
                ],
                [
                    "`invariant_stable`",
                    str(summary.get("invariant_stable", 0)),
                    "the wording changed, every Tier 1 outcome held. **Not a finding**",
                ],
                [
                    "`divergent`",
                    str(summary.get("divergent", 0)),
                    "a Tier 1 outcome changed between passes. **A finding**",
                ],
                [
                    "`not_comparable`",
                    str(summary.get("not_comparable", 0)),
                    "nothing to compare; see the reasons below",
                ],
            ],
        )
    )

    if check.get("partial"):
        out.append(f"*{check['partial']}.*")
        out.append("")

    divergent = [
        record
        for record in check.get("detail", {}).get("per_probe", [])
        if record.get("status") == FAIL
    ]
    if not divergent:
        out.append(
            f"No Tier 1 outcome changed between passes. Answers that differed in "
            f"wording are counted above and are **not** findings — a generative system "
            f"rewording an answer is not a defect, and reporting it as one is the "
            f"fastest way to lose the rest of this document."
        )
        out.append("")
        return out

    out.append(
        f"### {len(divergent)} {_plural(len(divergent), 'probe')} answered differently "
        f"across passes"
    )
    out.append("")
    out.append(
        "Each is reported with both texts and the diff. The finding is that the same "
        "question produced different outcomes, so it is unsafe to conclude anything "
        "from a single observation of these probes — in either direction."
    )
    out.append("")

    for record in divergent:
        out.append(f"**`{record['probe_id']}`** — {record['passes_compared']} passes compared")
        out.append("")
        for name, series in sorted((record.get("changed") or {}).items()):
            out.append(f"- `{name}`: {' → '.join(series)}")
        out.append("")
        if record.get("answers_identical"):
            out.append(
                "> [!IMPORTANT]"
            )
            out.append(
                "> The answer text was byte-identical across these passes and the "
                "outcome still moved. The change is below the answer — in what was "
                "retrieved or cited — so an output-level comparison would have found "
                "nothing here."
            )
            out.append("")
        if record.get("diff"):
            a, b = record.get("diff_passes", [1, 2])
            out.append(f"Pass {a} against pass {b}:")
            out.append("")
            out.append("```diff")
            out.extend(record["diff"].splitlines())
            out.append("```")
            out.append("")

    return out


def _measurement_section(check: dict[str, Any]) -> list[str]:
    """A measurement, printed as a distribution and never as a verdict (§8.2 #15).

    Median and p95, never a single figure: one number for a latency is a claim about a
    system, and the spread is the only part of it a reader can use.
    """
    detail = check.get("detail", {})
    out = [
        f"### `{check['check']}` — measurement, no pass condition",
        "",
        f"**Recipe:** {check['recipe']}",
        "",
    ]
    if check.get("limit"):
        out.append("> [!NOTE]")
        out.append(f"> {check['limit']}.")
        out.append("")

    distributions = detail.get("distributions") or {}
    rows = []
    for name in ("ttfb", "total"):
        summary = distributions.get(name) or {}
        rows.append(
            [
                f"`{name}`",
                str(summary.get("observations", 0)),
                _ms(summary.get("median_ms")),
                _ms(summary.get("p95_ms")),
                _ms(summary.get("min_ms")),
                _ms(summary.get("max_ms")),
            ]
        )
    out.extend(
        _table(["", "observations", "median", "p95", "min", "max"], rows)
    )

    not_captured = (distributions.get("ttfb") or {}).get("not_captured", 0)
    if not_captured:
        out.append(
            f"Time to first byte was not captured on {not_captured} "
            f"{_plural(not_captured, 'record')}, so the gap this measurement is usually "
            f"read for was not observed there."
        )
        out.append("")

    inference = detail.get("inference")
    if inference:
        out.append(
            f"**Reading — register `{inference['register']}`.** "
            f"{inference['reading']}, comparing `{inference['baseline_probe']}` with "
            f"`{inference['contradictory_probe']}`."
        )
        out.append("")
        out.append("> [!IMPORTANT]")
        out.append(f"> {inference['limit']}.")
        out.append("")
    if check.get("partial"):
        out.append(f"**Partial:** {check['partial']}")
        out.append("")
    return out


def _ms(value: Any) -> str:
    return "—" if value is None else f"{int(value)} ms"


def _tier2_section(check: dict[str, Any]) -> list[str]:
    dist = check["distribution"]
    out = [f"### `{check['check']}`", ""]
    out.append(
        f"**Instrument:** `{dist['instrument']}` · **line:** {dist['line']} "
        f"({dist['line_reads']})"
    )
    out.append("")
    out.append(f"**Measures:** {dist['measures']}.")
    out.append("")
    out.append(f"> The line is {dist['line_is']}.")
    out.append("")
    out.append(
        f"{dist['on_the_failing_side']} of {dist['records_with_a_number']} scored "
        f"records fell on the failing side."
    )
    out.append("")
    out.extend(
        _table(
            ["Statistic", "Value"],
            [
                ["min", dist["min"]],
                ["median", dist["median"]],
                ["mean", dist["mean"]],
                ["max", dist["max"]],
            ],
        )
    )
    out.append("| Range | Count | |")
    out.append("|---|---|---|")
    out.extend(render_distribution(dist))
    out.append("")
    return out


def _not_run(report: dict[str, Any]) -> list[str]:
    rows = []
    for name, check in report["checks"].items():
        if check["status"] in (NOT_ELIGIBLE, NOT_CAPTURED):
            rows.append(
                [
                    f"`{name}`",
                    check["status"],
                    check.get("reason", check.get("partial", "—")),
                ]
            )
    out = (
        ["Every registered check ran.", ""]
        if not rows
        else [
            "Neither of these is a pass. A check absent from a report is "
            "indistinguishable from one that passed, which is why they are here.",
            "",
            *_table(["Check", "Status", "Why"], rows),
        ]
    )

    # Checks that ran and could not score part of their denominator. The ones that
    # produced a finding carry this inline in §2; the rest would carry it nowhere, and
    # a check that scored two records out of twelve is not the same claim as one that
    # scored twelve (F40).
    rendered_in_full = {
        name for name in report.get("tier1", []) if report["checks"][name]["status"] == FAIL
    }
    for name, check in report["checks"].items():
        # NOT_ELIGIBLE checks have no records to split. A check whose *status* is
        # NOT_CAPTURED does: it is in the table above with a single reason, and that
        # reason is exactly the one this breakdown exists to take apart.
        if name in rendered_in_full or check["status"] == NOT_ELIGIBLE:
            continue
        breakdown = _unscoreable(check)
        if breakdown:
            out.append("")
            out.append(f"#### `{name}` — records that could not be scored")
            out.append("")
            out.extend(breakdown)
    return out


def _unscoreable(check: dict[str, Any]) -> list[str]:
    """The unscoreable half of a check's denominator, split by what the answers did.

    Defect 20. `not_captured` as a bare count is the place where a system that said *"I
    could not produce a grounded answer"* and one that asserted a figure from the wrong
    section of the same Act become one number. Both are outside the denominator and
    neither is a finding — but only one of them is a system behaving well, and a reader
    triaging the run has to be able to tell which records are which without opening the
    response file.
    """
    groups = (check.get("detail") or {}).get("not_captured_by_outcome") or []
    if not groups:
        return []

    total = sum(g["records"] for g in groups)
    out = [
        f"**{total} of {total + check['scored']} "
        f"{_plural(total + check['scored'], 'record')} could not be scored.** Not passes "
        f"and not failures: the answer never reached the value the check turns on. They "
        f"are split by what the answer did instead, because those are different events.",
        "",
    ]
    rows = [
        [
            f"`{group['outcome']}`",
            group["records"],
            ", ".join(f"`{p}`" for p in group["probes"]),
        ]
        for group in groups
    ]
    out.extend(_table(["Outcome", "Records", "Probes"], rows))
    for group in groups:
        if group.get("reason"):
            out.append(f"- `{group['outcome']}` — {group['reason']}.")
    out.append("")

    # Per probe, never pooled. What each of these answers said instead is the whole
    # reason the split exists, and attributing one record's figure to another would be a
    # worse error than not printing it at all.
    asserted = [
        (probe, claims)
        for group in groups
        for probe, claims in (group.get("claims_by_probe") or {}).items()
    ]
    if asserted:
        out.append("**What those answers asserted instead.** Quoted from the response "
                   "file, excluding anything the question itself said:")
        out.append("")
        for probe, claims in asserted:
            out.append(f"- `{probe}` — {', '.join(f'`{c}`' for c in claims)}")
        out.append("")
    return out


def _reproduction(manifest: dict[str, Any]) -> list[str]:
    tool = manifest["tool"]
    inputs = manifest["inputs"]
    out = [
        "```bash",
        f"# 1. the build that produced this report",
        (
            f"git checkout {tool['commit_sha']}"
            if tool["commit_sha"]
            else f"pip install legal-rag-audit=={tool['version']}"
        ),
        "pip install --require-hashes -r requirements/score.txt",
        "",
        "# 2. verify the inputs are the ones this report was scored from",
        "shasum -a 256 responses.jsonl probes.jsonl ground_truth.json",
        "",
        "# 3. rescore",
        "legal-rag-audit score --responses responses.jsonl \\",
        "                      --ground-truth ground_truth.json \\",
        "                      --probes probes.jsonl -o out/",
        "```",
        "",
        "The digests to compare against:",
        "",
    ]
    out.extend(
        _table(
            ["Artefact", "sha256"],
            [
                ["`responses.jsonl`", f"`{inputs['responses_hash']}`"],
                ["`probes.jsonl`", f"`{inputs['query_set_hash'] or '—'}`"],
                ["`ground_truth.json`", f"`{inputs['ground_truth_manifest_hash']}`"],
            ],
        )
    )
    for name, recipe in sorted((inputs.get("recipes") or {}).items()):
        out.append(f"**{name}** — {recipe}")
        out.append("")
    out.append(
        f"A rescore that reproduces this report yields findings digest "
        f"`{manifest['scoring']['findings_hash']}`."
    )
    out.append("")
    return out


def _limits(report: dict[str, Any], capture: dict[str, Any]) -> list[str]:
    manifest = report["manifest"]
    limits = [
        "Determinism is a property of the scoring, not of the target. Two runs "
        "against a non-deterministic system legitimately differ.",
        "Every count above is against the denominator printed beside it — probes "
        "declared eligible before the run, never the probes that happened to fail.",
        "Injection is scored by a demanded side effect appearing in the answer. That "
        "measures instruction-boundary override, not data exfiltration.",
    ]
    if capture["retrieved_chunks_captured"] is None:
        limits.append(
            "The response file does not say whether retrieved chunks were captured, "
            "and none were present. That is not the same as knowing they were not — "
            "no check could see below the answer either way."
        )
    elif not capture["retrieved_chunks_captured"]:
        limits.append(
            "Retrieved chunks were not captured, so no check could see below the "
            "answer. A finding suppressed by an output filter is indistinguishable "
            "from one that did not occur."
        )
    # §13. A report about an authorised-testing battery that cannot say who consented to
    # it is missing something a reader needs, and the gap has to be visible where they
    # are already looking for what the run does not establish.
    if manifest.get("not_recorded", {}).get("authorisation") and not manifest.get(
        "authorisation"
    ):
        limits.append(
            f"Authorisation: {manifest['not_recorded']['authorisation']}"
        )

    # §9.5 — corpora go stale because law moves. Printed as a limit rather than as a
    # footnote: it is the sentence that says when this report stops being current, and it
    # is the re-run trigger built into the artefact rather than chased by email.
    for trigger in manifest["run"].get("staleness_triggers") or []:
        limits.append(
            f"This corpus states a position that an amendment would falsify: {trigger}. "
            f"The run is evidence about the date it was made on."
        )
    if not capture["document_ids_supplied"]:
        limits.append(
            "No upload manifest was supplied, so citation identifiers could not be "
            "checked for membership against the documents actually indexed."
        )
    wrapped = manifest["capture"].get("probes_asked_wrapped") or []
    if wrapped:
        limits.append(
            f"{len(wrapped)} {_plural(len(wrapped), 'probe')} reached the target wrapped "
            f"in text that was not in the sealed probe file — a system preamble, a "
            f"formatting instruction, or similar: "
            f"{', '.join(f'`{p}`' for p in wrapped)}. The answers still answer our "
            f"questions and the findings stand; what does not stand is the claim that "
            f"those questions were put verbatim."
        )
    limits.append(
        "This report describes a response file. Its inputs — the corpus, the probes and "
        "the answer key — were digested before any answer existed and were recomputed "
        "here. The responses themselves carry no such guarantee: they were produced "
        "outside this software, and nothing in it can establish that what reached the "
        "file is what the target returned. That is a property of the producer holding "
        "custody, which is what makes the findings hard to dismiss as our harness "
        "prompting badly, and it cuts both ways."
    )
    if manifest["run"]["seed"] is None:
        limits.append(
            "The corpus carries fixed facts rather than seeded plants, so a key "
            "disclosed after this run remains valid for the next one. Per-engagement "
            "regeneration is what makes a repeat run meaningful."
        )
    elif "reproducible by anyone" in (manifest["run"].get("seed_source") or ""):
        limits.append(
            "**The plants came from the published demo seed.** Anyone can regenerate "
            "this corpus and this answer key, so nothing here turns on the invariants "
            "having been unguessable. This run demonstrates the method; it establishes "
            "nothing about any product."
        )
    if manifest["scoring"]["tier2_skipped"]:
        limits.append(
            "Tier 2 scoring was disabled for this run. Those checks did not execute "
            "and are recorded as not run, not as passes."
        )
    limits.append(
        "This diagnostic characterises the pipeline it was pointed at. It "
        "establishes nothing about production behaviour at scale, and nothing about "
        "any corpus other than the one whose digest is in §1."
    )
    return limits
