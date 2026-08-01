#!/usr/bin/env python3
"""Phase A acceptance gate: the README makes no unqualified claim.

Mechanical enforcement of V2_FULL_PLAN.md Appendix D. Four rules, checked per
paragraph, because scoping has to sit in the same paragraph as the claim — a footnote
does not count (§4.2).

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

README = Path(__file__).resolve().parents[1] / "README.md"

BANNED_WORDS = ["comprehensive", "robust", "best practice", "naive"]

# "simply" is banned; "simple"/"simpler" are not — they are sometimes the accurate word.
BANNED_PATTERNS = [r"\bsimply\b"]

DETERMINISM_TRIGGER = re.compile(r"determinis", re.IGNORECASE)
DETERMINISM_SCOPE = re.compile(r"scoring|scored|scorer", re.IGNORECASE)

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


def main() -> int:
    if not README.exists():
        print(f"FAIL: {README} not found")
        return 1

    text = README.read_text(encoding="utf-8")
    failures = []

    for line_no, block in paragraphs(text):
        if DETERMINISM_TRIGGER.search(block) and not DETERMINISM_SCOPE.search(block):
            failures.append(
                f"README.md:{line_no}: determinism asserted without scoping it to "
                f"scoring in the same paragraph"
            )
        if EXFIL_TRIGGER.search(block) and not EXFIL_SCOPE.search(block):
            failures.append(
                f"README.md:{line_no}: exfiltration claim not scoped to the local "
                f"path in the same paragraph"
            )

    for match in RATE_PATTERN.finditer(text):
        line_no = text[: match.start()].count("\n") + 1
        failures.append(
            f"README.md:{line_no}: 'hallucination rate' is not a check this tool "
            f"reports; use the mechanical check names (§10.5)"
        )

    lowered = text.lower()
    for word in BANNED_WORDS:
        for match in re.finditer(rf"\b{re.escape(word)}\b", lowered):
            line_no = text[: match.start()].count("\n") + 1
            failures.append(f"README.md:{line_no}: banned vocabulary: {word!r}")
    for pattern in BANNED_PATTERNS:
        for match in re.finditer(pattern, lowered):
            line_no = text[: match.start()].count("\n") + 1
            failures.append(
                f"README.md:{line_no}: banned vocabulary: {match.group(0)!r}"
            )

    if failures:
        print("FAIL: README claims are not scoped:")
        for f in sorted(set(failures)):
            print(f"  {f}")
        return 1

    print("  clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
