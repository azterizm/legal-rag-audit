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

**Two keys, not nine.** Before Phase D this module carried an enumerated list of result
keys — `leaked_content`, `trigger_phrases_found`, `missing_facts`, six more — because
each evaluator named its evidence differently and half of them nested it under `details`.
A bundle built on a guessed key list quietly omits whatever it does not recognise, and a
finding with no excerpt behind it is the exact thing the bundle exists to prevent. The
rewrite gave every Tier 1 evaluator one result shape (`evaluators._common.result`), so
this reads `appeared` and `absent` and nothing else, and a new evaluator cannot ship with
silently empty evidence.

Tier 1 only. Tier 2 findings are scored by an instrument against a line and their
evidence is the distribution (F24), not a quotation — quoting a sentence a model gave
0.83 to would dress a threshold decision as an observation.
"""

import re
from pathlib import Path
from typing import Any

from ..interchange import Probe, Response

#: Characters of context either side of a match. Enough to see the sentence it sat in,
#: short enough that the quotation is a quotation.
WINDOW = 160

APPEARED = "token_present"
ABSENT = "token_absent"

#: The two keys every Tier 1 evaluator populates. Read from the record itself and, for
#: safety, from a nested `details` block: a check that one day returns its evidence a
#: level down should produce a thin bundle, not a wrong one.
FOUND_KEY = "appeared"
MISSING_KEY = "absent"


def _fields(record: dict[str, Any]) -> list[dict[str, Any]]:
    nested = record.get("details")
    return [record, nested] if isinstance(nested, dict) else [record]


def _strings(value: Any) -> list[str]:
    """Flatten one evidence field into the strings it names, or nothing.

    Type-checked rather than assumed. An evaluator that put a count where a token
    belonged would otherwise land the number 2 in an evidence file as though the system
    had been asked to say "2".
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def _collect_key(record: dict[str, Any], key: str) -> list[str]:
    out: list[str] = []
    for field in _fields(record):
        for token in _strings(field.get(key)):
            if token not in out:
                out.append(token)
    return out


def _excerpt(answer: str, token: str) -> dict[str, Any]:
    """A window of the answer around the first occurrence of `token`.

    Word-boundary matched first, the same way the evaluators match, so the excerpt
    cannot point at a substring the check did not actually fire on.

    A token that is not in the answer is reported as such rather than dropped. Some
    checks read fields other than the answer — citation integrity matches document
    ids against the upload manifest, leakage reads retrieved chunks, entity masking
    looks in response metadata — and an evidence file that silently omitted those
    instances would undercount the very findings it exists to substantiate.
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
    appeared = [_excerpt(response.answer, t) for t in _collect_key(record, FOUND_KEY)]
    missing = _collect_key(record, MISSING_KEY)

    instance: dict[str, Any] = {
        "check": check,
        "probe_id": probe.probe_id,
        "pass_index": response.pass_index,
        "asked": probe.text,
        "tenant": probe.tenant,
        # Which of the check's own outcomes this was — `counterparty_swap`,
        # `silently_picked`, `vector_collision`. The excerpt shows what was said; this
        # says what the evaluator concluded from it, and the two should be checkable
        # against each other. Entity masking can conclude several at once, and all of
        # them are printed: an answer that both swapped a counterparty and omitted an
        # entity did two things, and naming one would understate it.
        "outcome": record.get("outcome")
        or ", ".join(record.get("outcomes") or []) or None,
    }

    if appeared:
        instance["kind"] = APPEARED
        instance["matches"] = appeared
        if missing:
            # Both, which happens on a swap: the wrong entity turned up *and* the right
            # one did not. Recorded rather than dropped — the omission is half the
            # finding.
            instance["expected_and_absent"] = missing
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
        if instance.get("outcome"):
            lines.append(f"**Outcome:** `{instance['outcome']}`")
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
            if instance.get("expected_and_absent"):
                lines.append(
                    "**And expected but absent:** "
                    + ", ".join(f"`{t}`" for t in instance["expected_and_absent"])
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
