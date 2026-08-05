#!/usr/bin/env python3
"""Scaffold a domain corpus from the spine (§9.5).

    python3 scripts/new_corpus.py employment
    python3 scripts/new_corpus.py acme-2026 -o ./corpora-private/

Writes a directory that is complete in every respect except the prose: every document
file exists with its slots already in place, every slot has a location line waiting for a
description, every probe has a line waiting for a question, and the whole thing is marked
`TODO` so it refuses to load until an author has been through it.

**This is the half-day claim, made checkable.** §9.5 says the fifth corpus in a practice
area is a template edit. The part of that which could quietly stop being true is the
*design* — which documents, which invariants, which questions — so none of it is left to
the author. What is left is writing plausible prose around slots somebody else placed, and
answering the two questions only a domain specialist can answer: what would make this
corpus stale, and which authority does a model know that these documents do not mention.

The skeleton is generated rather than copied so it cannot drift from the spine. A test
asserts `corpora/library/TEMPLATE/` is byte-identical to what this script produces, which
means adding a role to the spine breaks the build until the skeleton is regenerated.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from legal_rag_audit.corpora.library import DOCUMENTS, MANIFEST  # noqa: E402
from legal_rag_audit.corpora.spine import (  # noqa: E402
    BASE,
    MANDATORY,
    REVISION,
    SPINE,
)
from legal_rag_audit.probes.battery import BATTERY  # noqa: E402

HEADER = """\
# A domain corpus, scaffolded from corpora/spine.py.
#
# It does not load until every TODO below is replaced — including the ones inside
# documents/. That is deliberate: a placeholder reaching a target as a document body
# would produce findings about a document nobody wrote.
#
# Two of these fields cannot be scaffolded, because only somebody who knows the practice
# area can fill them:
#
#   staleness_triggers   what, if amended, makes this corpus wrong. An empty list is a
#                        legitimate answer only for a corpus that states no legal
#                        position at all.
#   out_of_corpus        an authority a base model reliably knows and no document here
#                        mentions. The loader checks the second half of that.
"""


def _a(kind: str) -> str:
    return f"{'an' if kind[0] in 'aeiou' else 'a'} {kind}"


def _wrap(text: str, width: int = 76, indent: str = "  # ") -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) + len(indent) > width:
            lines.append(indent + current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(indent + current)
    return lines


def manifest_for(name: str) -> str:
    out = [HEADER, f"corpus: {name}", "version: 1", "domain: TODO", "jurisdiction: TODO"]
    out += ["as_at: TODO  # ISO date: the law this corpus is stated as at", ""]
    out += ["description: >", "  TODO", ""]
    out += ["staleness_triggers:", "  - instrument: TODO", "    invalidates: TODO",
            "    watch: TODO", ""]
    out += ["out_of_corpus:", "  - TODO", "", "documents:"]

    for spec in SPINE:
        if spec.state == REVISION:
            continue
        out.append("")
        out.extend(_wrap(spec.purpose))
        out.append(f"  {spec.key}:")
        out.append(f"    filename: {spec.key}.txt")
        out.append("    identifier: TODO  # how a reader names this document")
        out.append("    slots:")
        for role in spec.roles:
            out.append(
                f"      {role.plant_id}: TODO  # {_a(role.kind)}; where in the document"
            )
        revision = next(
            (d for d in SPINE if d.key == spec.key and d.state == REVISION), None
        )
        if revision:
            out.append("    revision:")
            out.append("      slots:")
            for role in revision.roles:
                out.append(f"        {role.plant_id}: TODO  # {_a(role.kind)}")

    out += ["", "# One question per probe. `{plant:<id>}` fills in an identifier the",
            "# question could not otherwise retrieve on — never an expected answer.",
            "probes:"]
    for entry in BATTERY:
        out.append(f"  {entry.probe_id}: TODO  # {entry.family}, {entry.intent}")
    return "\n".join(out) + "\n"


def body_for(spec) -> str:
    lines = ["TODO — a document title", ""]
    lines.extend(f"TODO: {spec.purpose}".split(". ")[:1])
    lines.append("")
    for role in spec.roles:
        lines.append(f"TODO surrounding prose: @@{role.plant_id}@@")
    lines.append("")
    return "\n".join(lines) + "\n"


README = """\
# {name} — scaffolded, not yet authored

Generated by `scripts/new_corpus.py`. Replace every `TODO` and this file.

`legal-rag-audit plant --corpus <path to this directory>` refuses it until you have,
naming what is left — so the way to author it is to run that command repeatedly and fix
what it tells you.

## What to write, and what not to

Do not design anything. The documents, the invariants and the questions are fixed by
[`../../spine.py`](../../spine.py), and the reason they are fixed is that a corpus which
varied them would score against different checks under the same names. Write prose that
makes each document plausible in this practice area, and word each question the way
somebody in this practice area would ask it.

Two things do need judgment:

- **`staleness_triggers`** — which instruments, if amended, make this corpus wrong. This
  is the re-run trigger built into the artefact rather than chased by email (§9.5).
- **`out_of_corpus`** — an authority a base model reliably knows and no document here
  mentions. The loader checks the second half of that claim; the first half is yours.

## What this corpus will and will not establish

Write that section here before you finish, and be specific. Every corpus in this library
carries one, because the sentence a report needs most is the one that says what it does
not cover.
"""


def write(name: str, out: Path) -> None:
    documents = out / DOCUMENTS
    documents.mkdir(parents=True, exist_ok=True)
    (out / MANIFEST).write_text(manifest_for(name), encoding="utf-8")
    (out / "README.md").write_text(README.format(name=name), encoding="utf-8")
    for spec in SPINE:
        target = documents / f"{spec.key}.txt"
        if spec.state == REVISION:
            (documents / REVISION).mkdir(exist_ok=True)
            target = documents / REVISION / f"{spec.key}.txt"
        target.write_text(body_for(spec), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="the corpus name, e.g. `employment`")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="where to write it. Default: the shipped library, under <name>/",
    )
    args = parser.parse_args()

    out = (
        Path(args.output) / args.name
        if args.output
        else REPO_ROOT / "src" / "legal_rag_audit" / "corpora" / "library" / args.name
    )
    if out.exists() and any(out.iterdir()):
        print(f"{out} already exists and is not empty. Refusing to overwrite.")
        return 2

    write(args.name, out)
    base = sum(1 for s in SPINE if s.state == BASE)
    print(f"\n  {out}")
    print(f"  {base} documents, {len(BATTERY)} probes, all TODO.")
    print(f"  Mandatory elements, already placed: {', '.join(MANDATORY)}.")
    print("\n  Next:")
    print(f"    legal-rag-audit plant --corpus {out} -o /tmp/check\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
