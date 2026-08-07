"""Inter-pass divergence (V2_FULL_PLAN.md §8.3, F22).

Not an evaluator — a pass over all of them. Every other check asks *did the system do
the right thing*; this one asks *did it do the same thing twice*, and the answer is a
finding in its own right.

**Why this is the phase that turns a liability into a finding.** Without it, a target
whose answers vary between identical questions makes the harness look flaky: two runs
disagree, and the reader's first thought is that the tool is unreliable rather than that
the system is. Scoring here is deterministic and asserted to be (NF2). Target systems
typically are not. Naming that difference is the only way the report can survive the
first time a vendor re-runs the battery and gets a different number.

Three classifications, from §8.3:

* **`identical`** — byte-equal after whitespace normalisation.
* **`invariant_stable`** — the prose differs, every Tier 1 outcome is the same. **Not a
  finding.** Flagging ordinary phrasing variation as failure is the fastest way to lose
  a report, and a generative system rewording an answer is not a defect.
* **`divergent`** — a Tier 1 invariant outcome changed between passes. A Tier 1 finding
  (`response_divergence`), reported with both texts and the diff.

*What counts as the same outcome* is `signature_of` below, and it is finer than the
check's status: a refusal and a wrongly-asserted figure are both NOT_CAPTURED and are not
the same event (defect 32).

And a fourth this module adds, because §8.3's three assume there is something to
compare: **`not_comparable`** — fewer than two scored passes. It is not `identical`, and
recording it as such would let a single-pass run read as evidence of stability. Same rule
as F40 everywhere else: an absent measurement and a clean one must not print the same.

**Two ordering decisions worth arguing with.**

*Outcomes are compared before text.* §8.3 lists the three as though equal answers imply
equal outcomes. They do not: several Tier 1 checks read fields other than the answer —
leakage reads retrieved chunks, citation integrity reads document ids — so a system can
return a byte-identical answer over a different retrieval and change a verdict. That is a
divergence, and the more interesting kind, so it is classified as one and the coincidence
is recorded rather than smoothed away.

*Tier 2 outcomes are excluded.* A cosine similarity of 0.851 on one pass and 0.849 on the
next crosses a line **we** set, and reporting that as the target's non-determinism would
be attributing our own threshold to their system. Measurements are excluded for the same
reason from the other direction: a check with no pass condition has no outcome to
diverge, and latency varies between passes by construction.
"""

import difflib
from dataclasses import dataclass, field
from typing import Any, Optional

#: The four classifications. `not_comparable` is not one of §8.3's three; see above.
IDENTICAL = "identical"
INVARIANT_STABLE = "invariant_stable"
DIVERGENT = "divergent"
NOT_COMPARABLE = "not_comparable"

FAIL = "FAIL"

#: How much of each answer the evidence carries. Both texts in full is what §8.3 asks
#: for; this bounds a pathological case where a target returns a novel per pass.
MAX_TEXT = 4000


def normalise(text: str) -> str:
    """Whitespace-normalised, case preserved.

    Case is not whitespace. An answer that says "the agreement" on one pass and "The
    Agreement" on the next is a different answer, and folding it away here would report
    a system as byte-stable on the strength of our own normalisation.
    """
    return " ".join((text or "").split())


@dataclass(frozen=True)
class ProbeVariance:
    """What happened to one probe across its passes."""

    probe_id: str
    classification: str
    #: Passes that reached a comparison. Records lost to a transport error never reach
    #: an evaluator, so they are absent here rather than counted as agreement.
    passes_compared: int
    #: check -> the outcome on each compared pass, for checks whose outcome moved.
    #: Only the ones that changed: listing fifteen stable checks beside the one that
    #: moved buries the finding in its own evidence.
    changed: dict[str, list[str]] = field(default_factory=dict)
    #: True when the outcome moved while the answer text did not — the retrieval layer
    #: changed underneath an identical answer. Rare, and worth seeing.
    answers_identical: bool = False
    #: Why nothing could be compared. Present exactly when `not_comparable`.
    reason: Optional[str] = None
    #: The two answers the diff is taken over, and which passes they are. Carried on
    #: divergence only.
    #:
    #: The pair is chosen as the first adjacent passes whose outcomes disagree, not the
    #: first and last. A probe that failed on pass 2 and recovered on pass 3 has
    #: identical first and last answers, so diffing the ends would print an empty diff
    #: beside a finding — the reader would be shown nothing and told it was evidence.
    texts: tuple[str, ...] = ()
    diff_passes: tuple[int, int] = ()

    @property
    def is_finding(self) -> bool:
        return self.classification == DIVERGENT


def invariant_checks(checks: list[dict[str, Any]]) -> list[str]:
    """The checks whose outcome counts as an invariant (§8.3).

    Tier 1, excluding measurements and excluding this check itself. Read off the scored
    results rather than hardcoded, so an evaluator added later is covered without anyone
    remembering to add it here — and one reclassified to Tier 2 leaves without anyone
    remembering to remove it.
    """
    return sorted(
        c["check"]
        for c in checks
        if c["tier"] == 1
        and not c.get("measurement")
        and not c.get("cross_cutting")
        and c.get("detail", {}).get("per_probe")
    )


def signature_of(record: dict[str, Any]) -> str:
    """What counts as *the same outcome* for one record on one pass (defect 32).

    Status alone is not enough, and the third live run is why. A target asked the same
    dated question three times refused twice and then asserted a figure — a wrong one —
    on the third. All three records are `NOT_CAPTURED`, so a comparison on status called
    that **stable**. It is the opposite of stable, and *an honest refusal and a wrong
    figure must not print the same* is the rule this project already fixed once, for
    `point_in_time`, as defect 21. The split it produced was never wired through to
    here, so the finer signal existed and nothing looked at it.

    The signature therefore carries, in order of coarseness:

    * `status` — PASS / FAIL / NOT_CAPTURED, as before;
    * `outcome` — which kind of not-a-pass it was, so declining and asserting-something-
      else are different events;
    * `claims_offered` — the values asserted, so two different wrong figures are two
      different answers rather than one shrug repeated.

    No false-positive risk against a correct system: `claims_offered` is populated only
    on the neither-version outcome, so a record that passes contributes an empty list
    and two passing passes still compare equal. A system that answers correctly three
    times in three different sentences stays `invariant_stable`, which is what §8.3
    wants and what keeps this check worth reading.

    It is written to be read, not just compared. The signature is what the attestation
    prints in `PASS → FAIL → PASS`, so a divergence between two flavours of the same
    status has to say which flavours, or the report would show a probe changing from
    `NOT_CAPTURED` to `NOT_CAPTURED` and look broken. A record carrying no outcome —
    every check other than `point_in_time` — renders as the bare status, exactly as it
    did before this existed.
    """
    status = str(record.get("status"))
    outcome = record.get("outcome")
    # A pass is a pass, whatever flavour. `point_in_time` distinguishes `version_correct`
    # from `version_correct_with_context` — an answer that gave the right figure for the
    # date and also said what it later became — and that check's own stated limit is that
    # carrying both versions is *more than was asked for, not less*. Refining here would
    # report a system that answered correctly three times as having diverged, which is
    # the false positive §14.2 makes the release blocker, and it would pad a real finding
    # with a non-event. The conflation worth breaking is inside NOT_CAPTURED, where a
    # refusal and a wrongly-asserted figure look identical.
    if not outcome or status == "PASS":
        return status
    claims = [str(c) for c in (record.get("claims_offered") or [])]
    inner = f"{outcome}: {', '.join(sorted(claims))}" if claims else str(outcome)
    return f"{status} ({inner})"


def _outcomes_by_pass(
    checks: list[dict[str, Any]], names: list[str]
) -> dict[str, dict[int, dict[str, str]]]:
    """probe_id -> pass_index -> {check: signature}."""
    table: dict[str, dict[int, dict[str, str]]] = {}
    wanted = set(names)
    for check in checks:
        if check["check"] not in wanted:
            continue
        for record in check.get("detail", {}).get("per_probe", []):
            probe_id = record.get("probe_id")
            pass_index = record.get("pass_index")
            if probe_id is None or pass_index is None:
                continue
            table.setdefault(probe_id, {}).setdefault(pass_index, {})[
                check["check"]
            ] = signature_of(record)
    return table


def classify_probe(
    probe_id: str,
    answers: dict[int, str],
    outcomes: dict[int, dict[str, str]],
) -> ProbeVariance:
    """Classify one probe from its per-pass answers and per-pass Tier 1 outcomes."""
    answered = sorted(answers)

    if len(answered) < 2:
        return ProbeVariance(
            probe_id=probe_id,
            classification=NOT_COMPARABLE,
            passes_compared=len(answered),
            reason=(
                "one scored pass — divergence needs two. This is not a finding of "
                "stability; nothing was compared"
                if len(answered) == 1
                else "no usable record — nothing was compared"
            ),
        )

    texts = {p: normalise(answers[p]) for p in answered}
    identical = len({*texts.values()}) == 1

    passes = sorted(set(answers) & set(outcomes))
    if len(passes) < 2:
        # Answered more than once, but with no Tier 1 invariant outcome to compare —
        # a probe eligible only for Tier 2 checks or for a measurement, or one whose
        # Tier 1 checks did not run. `identical` is still decidable and still true, so
        # it is reported; the rest is not, and saying "stable" here would be asserting
        # something about invariants that were never evaluated.
        if identical:
            return ProbeVariance(
                probe_id=probe_id,
                classification=IDENTICAL,
                passes_compared=len(answered),
            )
        return ProbeVariance(
            probe_id=probe_id,
            classification=NOT_COMPARABLE,
            passes_compared=len(answered),
            reason=(
                f"{len(answered)} answers, differing, but no Tier 1 invariant outcome "
                f"to compare them by — this probe is eligible only for checks whose "
                f"result is not an invariant (Tier 2, or a measurement), or its Tier 1 "
                f"checks did not run. The wording changed; whether anything else did is "
                f"not established"
            ),
        )

    changed: dict[str, list[str]] = {}
    first = outcomes[passes[0]]
    for name in sorted({k for p in passes for k in outcomes[p]}):
        series = [outcomes[p].get(name) for p in passes]
        # A check that scored on some passes and not others has moved: the absence is
        # itself the difference, and calling it agreement would hide it.
        if any(value != series[0] for value in series) or name not in first:
            changed[name] = [value or "not scored" for value in series]

    if changed:
        # The first adjacent pair that actually disagrees. See `diff_passes`.
        pair = (passes[0], passes[1])
        for left, right in zip(passes, passes[1:]):
            if outcomes[left] != outcomes[right]:
                pair = (left, right)
                break
        return ProbeVariance(
            probe_id=probe_id,
            classification=DIVERGENT,
            passes_compared=len(passes),
            changed=changed,
            answers_identical=identical,
            texts=(texts[pair[0]][:MAX_TEXT], texts[pair[1]][:MAX_TEXT]),
            diff_passes=pair,
        )

    return ProbeVariance(
        probe_id=probe_id,
        classification=IDENTICAL if identical else INVARIANT_STABLE,
        passes_compared=len(passes),
    )


def diff(
    before: str, after: str, from_label: str = "before", to_label: str = "after"
) -> str:
    """A unified diff of two answers, word-wrapped to sentences.

    Split on sentence-ish boundaries rather than on the single line an answer usually
    is, because a line diff of two paragraphs prints both paragraphs and shows nothing.
    """
    def units(text: str) -> list[str]:
        out, current = [], []
        for word in normalise(text).split(" "):
            current.append(word)
            if word.endswith((".", "!", "?", ":", ";")):
                out.append(" ".join(current))
                current = []
        if current:
            out.append(" ".join(current))
        return out

    return "\n".join(
        difflib.unified_diff(
            units(before),
            units(after),
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
    )


def analyse(
    checks: list[dict[str, Any]],
    answers: dict[str, dict[int, str]],
    eligible: list[str],
) -> dict[str, Any]:
    """The variance pass over one run.

    `checks` are the already-scored results of every other check — this runs last
    because it is a pass over them. `answers` is probe_id -> pass_index -> answer text.
    `eligible` is the probes the probe file declared eligible, which is the denominator
    (F39): probes that produced no usable record still count against it as uncompared.
    """
    names = invariant_checks(checks)
    table = _outcomes_by_pass(checks, names)

    results = [
        classify_probe(probe_id, answers.get(probe_id, {}), table.get(probe_id, {}))
        for probe_id in eligible
    ]

    counts = {
        IDENTICAL: 0,
        INVARIANT_STABLE: 0,
        DIVERGENT: 0,
        NOT_COMPARABLE: 0,
    }
    for result in results:
        counts[result.classification] += 1

    return {
        "invariant_checks": names,
        "counts": counts,
        "results": results,
        "compared": sum(1 for r in results if r.classification != NOT_COMPARABLE),
        "divergent": [r for r in results if r.is_finding],
    }
