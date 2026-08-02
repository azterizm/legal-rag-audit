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
    if manifest["run"]["passes"] < 2:
        add(
            "This run fired each probe once, so inter-pass divergence was not "
            "measured. Variance reporting arrives with multi-pass execution."
        )
        add("")

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
        ["Corpus", f"`{inputs['corpus_hash']}`" if inputs["corpus_hash"] else "—"],
        ["Probe file", f"`{inputs['query_set_hash']}`" if inputs["query_set_hash"] else "—"],
        ["Ground truth", f"`{inputs['ground_truth_manifest_hash']}`"],
        ["Responses", f"`{inputs['responses_hash']}`"],
        ["Findings digest", f"`{manifest['scoring']['findings_hash']}`"],
        ["Passes", manifest["run"]["passes"]],
        ["Remote scoring", "false — enforced, not asserted"],
    ]
    out = _table(["Field", "Value"], rows)

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
    if check.get("partial"):
        out.append(f"**Partial:** {check['partial']}")
        out.append("")

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
    if not rows:
        return ["Every registered check ran.", ""]
    return [
        "Neither of these is a pass. A check absent from a report is "
        "indistinguishable from one that passed, which is why they are here.",
        "",
        *_table(["Check", "Status", "Why"], rows),
    ]


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
    if not capture["document_ids_supplied"]:
        limits.append(
            "No upload manifest was supplied, so citation identifiers could not be "
            "checked for membership against the documents actually indexed."
        )
    if manifest["run"]["seed"] is None:
        limits.append(
            "The corpus carries fixed facts rather than seeded plants, so a key "
            "disclosed after this run remains valid for the next one. Per-engagement "
            "regeneration is what makes a repeat run meaningful."
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
