#!/usr/bin/env python3
"""Phase A acceptance gate: no published document makes an unqualified claim.

Mechanical enforcement of V2_FULL_PLAN.md Appendix D. Four rules, checked per
paragraph, because scoping has to sit in the same paragraph as the claim — a footnote
does not count (§4.2).

Widened in Phase B2 from the README to every published document. The first run over the
new set found `docs/responses-schema.md` asserting *"nothing is sent anywhere"* with no
scope attached, in a file handed to third parties implementing the interchange format —
a stronger claim than the README was allowed to make, in a document nobody was checking.

    1. Determinism is a property of the scoring. Any paragraph asserting it must say so
       in the same paragraph.
    2. Zero-exfiltration claims are true on the local path. Any paragraph asserting it
       must scope it in the same paragraph.
    3. "hallucination rate" is not a metric this tool reports. The checks have
       mechanical names (§10.5).
    4. Banned vocabulary (Measurement Language Guide §4) does not appear.

Run directly or via scripts/check_no_remote_scoring.sh.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Every published document that makes a claim about the tool, not only the README.
#:
#: Phase B2 added SECURITY.md and docs/threat-model.md — two documents whose entire
#: subject is what the tool does and does not do, written for the reader least willing
#: to take any of it on trust. Leaving them outside the gate would have put the
#: strongest claims in the repository under the weakest scrutiny in it.
#: Phase F2 added docs/harness-verification.md. It is the one document whose whole
#: subject is how well our own instrument works, so a claim in it that outran its
#: evidence would be the most damaging kind available — and it is exactly the document a
#: reader who distrusts the rest will turn to first.
#: Phase U added the three documents the README was split into, and CONTRIBUTING.md.
#: Moving a claim out of a gated file and into an ungated one would defeat the gate
#: silently — the split was a restructure, and a restructure must not be a way to launder
#: an unqualified sentence into a document nobody checks.
DOCUMENTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "docs" / "configuration.md",
    REPO_ROOT / "docs" / "corpora.md",
    REPO_ROOT / "docs" / "design.md",
    REPO_ROOT / "docs" / "threat-model.md",
    REPO_ROOT / "docs" / "responses-schema.md",
    REPO_ROOT / "docs" / "harness-verification.md",
    REPO_ROOT / "docs" / "authoring-a-corpus.md",
    REPO_ROOT / "docs" / "authorisation-and-retention.md",
    REPO_ROOT / "docs" / "hardened-run.md",
)

BANNED_WORDS = ["comprehensive", "robust", "best practice", "naive"]

# "simply" is banned; "simple"/"simpler" are not — they are sometimes the accurate word.
BANNED_PATTERNS = [r"\bsimply\b"]

DETERMINISM_TRIGGER = re.compile(r"determinis", re.IGNORECASE)
DETERMINISM_SCOPE = re.compile(r"scoring|scored|scorer", re.IGNORECASE)

#: Removed before the trigger runs, for the same reason EXFIL_TRIGGER matches the
#: assertion rather than the word: *non-determinism* asserts the opposite of the claim
#: this rule guards, and it is nearly always said about a target rather than about us.
#: NF2's whole point is that the two differ — scoring is deterministic, target systems
#: typically are not — so a gate that could not tell them apart would force a scoping
#: clause onto the sentence drawing the distinction. A paragraph that also asserts our
#: own determinism still trips, because only this negation is removed.
NOT_A_DETERMINISM_CLAIM = re.compile(r"non[- ]?determinis\w*", re.IGNORECASE)

# Triggers on the *assertion*, not on the word. Naming exfiltration as something the
# harness does not establish (the injection proxy limit) is a limit, not a claim, and
# must not be forced to carry a scoping clause it does not need.
EXFIL_TRIGGER = re.compile(
    r"zero data exfiltration"
    r"|no data (?:leaves|is transmitted|is sent)"
    r"|nothing (?:leaves|is transmitted|is sent)"
    r"|does not (?:transmit|phone home|exfiltrate)"
    r"|no telemetry"
    r"|no phone[- ]home",
    re.IGNORECASE,
)
EXFIL_SCOPE = re.compile(r"\blocal\b|no remote|offline|target endpoint", re.IGNORECASE)

RATE_PATTERN = re.compile(r"hallucination rate", re.IGNORECASE)


def paragraphs(text: str):
    """Yield (first_line_number, paragraph_text) for blank-line-separated blocks."""
    line_no = 1
    for block in re.split(r"\n\s*\n", text):
        yield line_no, block
        line_no += block.count("\n") + 2


def check(path: Path) -> list[str]:
    """Every Appendix D rule, against one document."""
    name = path.relative_to(REPO_ROOT)
    text = path.read_text(encoding="utf-8")
    failures = []

    for line_no, block in paragraphs(text):
        claimed = NOT_A_DETERMINISM_CLAIM.sub("", block)
        if DETERMINISM_TRIGGER.search(claimed) and not DETERMINISM_SCOPE.search(block):
            failures.append(
                f"{name}:{line_no}: determinism asserted without scoping it to "
                f"scoring in the same paragraph"
            )
        if EXFIL_TRIGGER.search(block) and not EXFIL_SCOPE.search(block):
            failures.append(
                f"{name}:{line_no}: exfiltration claim not scoped to the local "
                f"path in the same paragraph"
            )

    for match in RATE_PATTERN.finditer(text):
        line_no = text[: match.start()].count("\n") + 1
        failures.append(
            f"{name}:{line_no}: 'hallucination rate' is not a check this tool "
            f"reports; use the mechanical check names (§10.5)"
        )

    lowered = text.lower()
    for word in BANNED_WORDS:
        for match in re.finditer(rf"\b{re.escape(word)}\b", lowered):
            line_no = text[: match.start()].count("\n") + 1
            failures.append(f"{name}:{line_no}: banned vocabulary: {word!r}")
    for pattern in BANNED_PATTERNS:
        for match in re.finditer(pattern, lowered):
            line_no = text[: match.start()].count("\n") + 1
            failures.append(f"{name}:{line_no}: banned vocabulary: {match.group(0)!r}")

    return failures


def main() -> int:
    failures: list[str] = []

    for path in DOCUMENTS:
        if not path.exists():
            failures.append(f"{path.relative_to(REPO_ROOT)}: not found")
            continue
        failures.extend(check(path))

    if failures:
        print("FAIL: published claims are not scoped:")
        for f in sorted(set(failures)):
            print(f"  {f}")
        return 1

    print(f"  clean ({len(DOCUMENTS)} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
