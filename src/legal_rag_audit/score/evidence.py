"""The evidence bundle: what the system actually said, verbatim (F41).

A finding that says *"cross-tenant leakage: 3 instances"* is a number the reader has
to take on trust. A finding that quotes the sentence, names the canary inside it, and
says which probe and which pass produced it is something they can check against their
own logs. The bundle exists so a Tier 1 finding can be disputed on the facts rather
than on our arithmetic — which is the only kind of dispute this method can survive.

Two shapes of evidence, and conflating them would misdescribe half the findings:

* **A token appeared that should not have.** The evidence is the excerpt: a window of
  the answer around the match, with the match located. Short, exact, damning.
* **A token that should have appeared did not.** There is no excerpt to take — the
  evidence is the *whole answer*, because the claim is about everything it did say.
  Calling that an "excerpt" would imply we chose a fragment, and the reader would be
  right to ask what was in the rest.

Tier 1 only. Tier 2 findings are scored by an instrument against a line and their
evidence is the distribution (F24), not a quotation — quoting a sentence a model gave
0.83 to would dress a threshold decision as an observation.
"""

import re
from pathlib import Path
from typing import Any, Optional

from ..interchange import Probe, Response

#: Characters of context either side of a match. Enough to see the sentence it sat in,
#: short enough that the quotation is a quotation.
WINDOW = 160

APPEARED = "token_present"
ABSENT = "token_absent"

#: Result keys holding "these are the strings that appeared and should not have".
#: An enumerated list, taken from the evaluators as they are actually written, rather
#: than a heuristic scan for anything list-shaped — a heuristic would start quoting a
#: field the moment an evaluator gained one that happens to hold strings.
#:
#: `tests/test_report.py` asserts every evaluator that can fail contributes a key here
#: or in MISSING_KEYS, so a new evaluator cannot ship with silently empty evidence.
FOUND_KEYS = (
    "leaked_content",  # leakage
    "leaked_keywords",  # routing
    "leaked_forbidden",  # disambiguation
    "trigger_phrases_found",  # injection
    "found_canaries",  # parametric bleed
    "invalid_citations",  # citation integrity — ids, not answer text
    "swaps",  # entity masking
    "metadata_leaks",  # entity masking
    "conflations",  # structural
)

#: The mirror: strings that should have been there and were not.
MISSING_KEYS = (
    "missing",  # synthesis, entity masking
    "missing_facts",  # structural
    "missing_expected",  # disambiguation
    "expected",  # memory (a string); conflict returns an int here and is ignored
)

#: Several evaluators nest the evidence under `details` and several do not. Both are
#: searched rather than one normalised, because normalising would mean editing
#: seventeen evaluators that Phase D rewrites anyway.
def _fields(record: dict[str, Any]) -> list[dict[str, Any]]:
    nested = record.get("details")
    return [record, nested] if isinstance(nested, dict) else [record]


def _per_fact_absences(record: dict[str, Any]) -> list[str]:
    """Attribution's own shape: a fact/source pair per row.

    Its failure is a third thing, and folding it into either of the two above would
    misdescribe it. An *orphaned claim* is a fact that appeared without its source —
    so the absent string is the source marker, not the fact. Taking every string in
    the row would name the facts that were correctly attributed as well.
    """
    absent = []
    for field in _fields(record):
        for row in field.get("per_fact") or []:
            if not isinstance(row, dict):
                continue
            fact, source = row.get("fact"), row.get("expected_source")
            if not row.get("fact_found") and isinstance(fact, str):
                absent.append(fact)
            elif not row.get("source_attributed") and isinstance(source, str):
                absent.append(source)
    return absent


def _strings(value: Any) -> list[str]:
    """Flatten a result field into the strings it names, or nothing.

    Type-checked rather than assumed, because the same key means different things in
    different evaluators — `expected` is a string in memory.py and a *count* in
    conflict.py. A collector that assumed would put the number 2 in an evidence file
    as though the system had been asked to say "2".
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                # entity masking's `swaps` are dicts. Take the values that are strings.
                out.extend(v for v in item.values() if isinstance(v, str))
            elif isinstance(item, (list, tuple)) and item:
                out.append(str(item[0]))
        return out
    return []


def _excerpt(answer: str, token: str) -> dict[str, Any]:
    """A window of the answer around the first occurrence of `token`.

    Word-boundary matched first, the same way the evaluators match, so the excerpt
    cannot point at a substring the check did not actually fire on.

    A token that is not in the answer is reported as such rather than dropped. Some
    checks read fields other than the answer — citation integrity matches document
    ids against the upload manifest, entity masking looks in response metadata — and
    an evidence file that silently omitted those instances would undercount the very
    findings it exists to substantiate.
    """
    match = re.search(rf"(?<!\w){re.escape(token)}(?!\w)", answer, re.IGNORECASE)
    if match is None:
        match = re.search(re.escape(token), answer, re.IGNORECASE)
    if match is None:
        return {
            "token": token,
            "found_in": "not the answer text",
            "excerpt": None,
            "note": (
                "this check reads a field other than the answer — see the check's "
                "`recipe` and its `detail` in report.json"
            ),
        }

    start = max(0, match.start() - WINDOW)
    end = min(len(answer), match.end() + WINDOW)
    return {
        "token": token,
        "found_in": "answer",
        "excerpt": answer[start:end],
        "truncated_before": start > 0,
        "truncated_after": end < len(answer),
        "offset_in_answer": match.start(),
    }


def _instance(
    check: str,
    probe: Probe,
    response: Response,
    record: dict[str, Any],
) -> dict[str, Any]:
    """One failing record, with the verbatim material behind it."""
    appeared: list[dict[str, Any]] = []
    missing: list[str] = []
    for field in _fields(record):
        for key in FOUND_KEYS:
            appeared.extend(
                _excerpt(response.answer, token) for token in _strings(field.get(key))
            )
        for key in MISSING_KEYS:
            missing.extend(_strings(field.get(key)))
    missing.extend(_per_fact_absences(record))

    instance: dict[str, Any] = {
        "check": check,
        "probe_id": probe.probe_id,
        "pass_index": response.pass_index,
        "asked": probe.text,
        "tenant": probe.tenant,
    }

    if appeared:
        instance["kind"] = APPEARED
        instance["matches"] = appeared
    elif missing:
        # Nothing to quote a window around. The whole answer is the evidence, because
        # the claim is about everything the system did say instead.
        instance["kind"] = ABSENT
        instance["expected_and_absent"] = missing
        instance["answer_in_full"] = response.answer
    else:
        # The evaluator failed the record without naming a token either way. Say so
        # rather than presenting the answer as if a specific string were at issue —
        # an evidence file that overstates what it shows is worse than a thin one.
        instance["kind"] = ABSENT
        instance["expected_and_absent"] = []
        instance["answer_in_full"] = response.answer
        instance["note"] = (
            "the evaluator recorded a failure without naming a token. The full answer "
            "is reproduced; the detail in report.json carries the evaluator's own "
            "output"
        )

    return instance


def collect(
    check: str,
    tier: int,
    detail: dict[str, Any],
    probes: dict[str, Probe],
    responses: dict[str, list[Response]],
) -> list[dict[str, Any]]:
    """Every failing instance of one Tier 1 check, with its verbatim material."""
    if tier != 1:
        return []

    instances = []
    for record in detail.get("per_probe", []):
        if record.get("status") != "FAIL":
            continue
        probe = probes.get(record.get("probe_id"))
        if probe is None:
            continue
        matching = [
            r
            for r in responses.get(probe.probe_id, [])
            if r.pass_index == record.get("pass_index")
        ]
        if not matching:
            continue
        instances.append(_instance(check, probe, matching[0], record))
    return instances


def write_bundle(directory: str | Path, by_check: dict[str, list[dict[str, Any]]]):
    """Write one Markdown file per failing check, plus a JSON index.

    Markdown because these get read by a person — often a person deciding whether to
    dispute the finding — and JSON because the same material has to be machine-
    readable for anyone rebuilding the report.
    """
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    written = {}

    for check, instances in sorted(by_check.items()):
        if not instances:
            continue
        path = out / f"{check}.md"
        path.write_text(_render(check, instances), encoding="utf-8")
        written[check] = {"file": f"evidence/{path.name}", "instances": len(instances)}

    return written


def _render(check: str, instances: list[dict[str, Any]]) -> str:
    lines = [
        f"# Evidence — `{check}`",
        "",
        f"{len(instances)} failing "
        f"{'instance' if len(instances) == 1 else 'instances'}, verbatim. Tier 1: no "
        f"model was involved in deciding any of these.",
        "",
    ]

    for number, instance in enumerate(instances, start=1):
        lines.append(
            f"## {number}. `{instance['probe_id']}` — pass {instance['pass_index']}"
        )
        lines.append("")
        if instance.get("tenant"):
            lines.append(f"**Asked as:** `{instance['tenant']}`")
            lines.append("")
        lines.append(f"**Asked:** {instance['asked']}")
        lines.append("")

        if instance["kind"] == APPEARED:
            lines.append("**A token appeared that should not have.**")
            lines.append("")
            for match in instance["matches"]:
                if match["excerpt"] is None:
                    lines.append(
                        f"`{match['token']}` — {match['found_in']}. {match['note']}."
                    )
                    lines.append("")
                    continue
                lines.append(
                    f"`{match['token']}`, at offset {match['offset_in_answer']}:"
                )
                lines.append("")
                prefix = "…" if match["truncated_before"] else ""
                suffix = "…" if match["truncated_after"] else ""
                lines.append(
                    "> " + prefix + match["excerpt"].replace("\n", "\n> ") + suffix
                )
                lines.append("")
        else:
            expected = instance.get("expected_and_absent") or []
            if expected:
                lines.append(
                    "**Expected and absent:** "
                    + ", ".join(f"`{token}`" for token in expected)
                )
            elif instance.get("note"):
                lines.append(f"**Note:** {instance['note']}")
            lines.append("")
            lines.append(
                "There is no excerpt to take — the claim is about what the answer did "
                "*not* contain, so the answer is reproduced in full:"
            )
            lines.append("")
            lines.append("> " + instance["answer_in_full"].replace("\n", "\n> "))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
