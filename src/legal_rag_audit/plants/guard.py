"""The plant collision guard — Tier 1's integrity condition (§3.2).

Tier 1 says: *a planted token either appeared or it did not.* That sentence is only true
while the token means one thing. Three ways it stops meaning one thing, and each is a
different wrong report:

1. **The value already occurs in the corpus.** Then its presence in an answer proves the
   system read a document, not that it leaked one. A false positive, and §14.2 makes a
   false positive a release blocker.
2. **Two plants overlap.** If plant A's value contains plant B's, every hit on A is also
   a hit on B, and the report attributes a leak to the wrong document. Checked in both
   directions, because presence is scored by substring.
3. **A generated citation resolves to a real authority.** Then *"your system cited a case
   that does not exist"* is false, and it is false about a named company.

A rejected value is regenerated from `plant_id + n` (§3.2) rather than adjusted, so the
accepted value stays a pure function of the seed and a third party can reproduce it.

The guard runs against the corpus **before planting** — the templates as authored. It has
to: after planting, every plant is in the corpus by construction, and checking then would
reject everything. That also makes the check reproducible, since the unplanted templates
ship with the tool.

`CHECKED` and `NOT_CHECKED` are the point of this module as much as the code is. They go
into the ground-truth manifest and onto the report, so the reader gets the scope of the
guarantee rather than the word "guarded".
"""

import re
from dataclasses import dataclass, field
from typing import Final, Optional

from .mint import CITATION, Minted, PlantError, mint
from .register import is_real_party

#: How many regenerations before the guard gives up on a plant id. Reached only when the
#: value space for a kind is genuinely exhausted, which is a design problem in the
#: battery — so it aborts with a diagnosis rather than quietly reusing a value.
MAX_ATTEMPTS: Final = 64

#: What the guard verifies. Written into every ground-truth manifest.
CHECKED: Final[tuple[str, ...]] = (
    "the value does not occur in the corpus as authored, before any planting",
    "the value neither contains nor is contained by any other plant in this run",
    "coined words — company names, citation party names — do not occur in the corpus, "
    "and are not in the bundled register of real parties and common surnames",
    "generated neutral citations carry a number at or above 4000, which is outside the "
    "range any division of the High Court has issued within a single year",
)

#: What it does not, stated in the same breath. §20.2 closes the first of these with
#: manual review of the generated citations in the first corpus of each domain; the
#: report is where that review is recorded, not this file.
NOT_CHECKED: Final[tuple[str, ...]] = (
    "the body of reported authority as a whole. Scoring is offline by construction "
    "(§5.1), so no lookup leaves this machine: a generated citation is checked "
    "structurally and against a small bundled register, never against a live database",
    "the target's own corpus. In existing-corpus mode we do not hold it, so a plant "
    "cannot be checked against documents we have never seen",
)


class PlantExhausted(PlantError):
    """A plant id could not be minted without a collision. A setup problem (NF9)."""


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


@dataclass
class Guard:
    """Accumulates accepted plants and rejects the ones that would blur a finding."""

    #: The corpus as authored, lowercased and concatenated. Substring containment is the
    #: test because presence scoring is substring containment; anything looser here would
    #: pass a value the scorer then fires on.
    corpus: str = ""
    #: Whole words of the corpus, for checking coined words without rejecting one for
    #: sitting inside an unrelated string.
    corpus_words: frozenset[str] = frozenset()
    #: Accepted value (lowercased) -> the plant id that owns it.
    taken: dict[str, str] = field(default_factory=dict)
    #: plant_id -> why each rejected attempt was rejected. Carried into the manifest so a
    #: regeneration is a recorded event rather than an invisible retry.
    rejections: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def over(cls, documents: dict[str, str]) -> "Guard":
        joined = "\n".join(documents.values()).lower()
        return cls(corpus=joined, corpus_words=frozenset(_tokens(joined)))

    def reject(self, minted: Minted) -> Optional[str]:
        """Why this value cannot be used, or None if it can."""
        lowered = minted.value.lower()

        if lowered in self.corpus:
            return "the value already occurs in the corpus as authored"

        for existing, owner in self.taken.items():
            if existing in lowered:
                return f"the value contains plant {owner!r} ({existing!r})"
            if lowered in existing:
                return f"the value is contained by plant {owner!r} ({existing!r})"

        for part in minted.parts:
            token = part.lower()
            if is_real_party(part):
                return f"the coined word {part!r} is in the register of real parties"
            if token in self.corpus_words:
                return f"the coined word {part!r} already occurs in the corpus"

        if minted.kind == CITATION and not _citation_number_is_out_of_range(minted.value):
            # Unreachable from `mint`, which draws from 4000 upwards. Kept because the
            # claim on the report — *this number is outside the range a real citation can
            # occupy* — should be enforced where it is stated, not left as a property of
            # a constant three modules away.
            return "the neutral citation number is inside the range real citations use"

        return None

    def accept(self, minted: Minted, plant_id: str) -> None:
        self.taken[minted.value.lower()] = plant_id

    def mint(self, kind: str, seed: str, plant_id: str) -> tuple[Minted, int]:
        """Mint `plant_id`, regenerating past collisions. Returns the value and attempt."""
        for attempt in range(MAX_ATTEMPTS):
            minted = mint(kind, seed, plant_id, attempt)
            reason = self.reject(minted)
            if reason is None:
                self.accept(minted, plant_id)
                return minted, attempt
            self.rejections.setdefault(plant_id, []).append(
                f"attempt {attempt}: {reason}"
            )

        raise PlantExhausted(
            f"{plant_id}: no {kind} plant survived {MAX_ATTEMPTS} regenerations.\n"
            f"  Last rejections: "
            f"{'; '.join(self.rejections.get(plant_id, [])[-3:])}\n"
            f"  The value space for this kind is exhausted for this corpus. `date` has\n"
            f"  the smallest space by nature — 28 x 12 x 46 — so a battery needing many\n"
            f"  distinct dates should plant figures or citations instead. Aborting: a\n"
            f"  reused value would make two findings indistinguishable."
        )

    def record(self) -> dict:
        """The guard's own account of itself, for the ground-truth manifest."""
        return {
            "checked": list(CHECKED),
            "not_checked": list(NOT_CHECKED),
            "plants": len(self.taken),
            "regenerations": sum(len(v) for v in self.rejections.values()),
            "regenerated": {k: list(v) for k, v in sorted(self.rejections.items())},
        }


_NEUTRAL = re.compile(r"\[\d{4}\]\s+EWHC\s+(\d+)\s+\(")


def _citation_number_is_out_of_range(value: str) -> bool:
    match = _NEUTRAL.search(value)
    return match is not None and int(match.group(1)) >= 4000
