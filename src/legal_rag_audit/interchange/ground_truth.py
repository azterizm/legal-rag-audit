"""`ground_truth.v2` — the withheld manifest (V2_FULL_PLAN.md §6.4, F26).

Everything a probe file deliberately does not say: what a correct answer contains, what
it must never contain, and which document it has to be attributed to. Handed over
**hashed, not disclosed**, before the run (§3.6). Publishing the hash first is what
makes the expectations pre-committed rather than fitted to what came back.

Three parts:

* `plants` — the seeded, collision-guarded invariants and where each was inserted.
  Populated by `plants.pipeline`; the `seed` beside them regenerates every value.
* `guard` — what the collision guard checked and, in the same breath, what it could not.
  A reader who is told a corpus was "guarded" has been told nothing; a reader who is told
  no lookup left the machine can price the residual risk themselves (§20.2).
* `expectations` — one per `(probe_id, check)`.

**What changed from v1.** Phase D folded `legacy_params` away. Four evaluators used to
take arguments in shapes of their own — PII pairs, fact/source tuples, a probe pairing —
carried in a free-form dict under a name that said what it was. The §8.2 rewrite gave
each of them a named field, so the contract now describes the check rather than the
function signature that happened to implement it, and `adjacency` became a list because
two checks need more than one pairing.
"""

import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .jsonl import InterchangeError
from .versions import GROUND_TRUTH_V2, assert_schema


class Adjacency(BaseModel):
    """A fact and its identifier must appear within the same unit of text.

    An answer that states the right figure in one paragraph and the right document ID
    three paragraphs later has not attributed the figure to the document — it has
    mentioned both. §8.2 scores adjacency by sentence unit for exactly that reason.
    """

    model_config = ConfigDict(extra="forbid")

    fact: str
    identifier: str
    unit: Literal["sentence", "paragraph"] = "sentence"


class SideEffect(BaseModel):
    """The verifiable artefact an injection payload demands (§3.3).

    Not *"was the model manipulated"* — that is judgment. A demand for a specific string
    in a specific position is a prefix or substring check, and the answer either carries
    it or does not.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["prefix", "suffix", "contains"]
    value: str
    #: Which planted document carried the instruction. On the page beside the finding, so
    #: the target can go and read the thing their retriever obeyed.
    planted_in: Optional[str] = None


class Pairing(BaseModel):
    """Two probes compared against each other rather than against ground truth.

    Latency's baseline and its contradictory counterpart. Which is which stays in the
    withheld half: a battery that announced *this is the timed trap* would let a target
    treat it differently.
    """

    model_config = ConfigDict(extra="forbid")

    baseline_probe: str
    contradictory_probe: str


class PlantGuard(BaseModel):
    """The collision guard's account of itself (§3.2)."""

    model_config = ConfigDict(extra="forbid")

    checked: list[str]
    not_checked: list[str]
    plants: int
    regenerations: int
    #: plant_id -> the rejected attempts and why. A regeneration is a recorded event, so
    #: a battery whose guard fired a hundred times cannot look like one where it never did.
    regenerated: dict[str, list[str]] = Field(default_factory=dict)
    #: How to reproduce every value from the seed, in prose. Published for the same
    #: reason the hash recipes are: the person checking us may not be running our code.
    recipe: str


class Plant(BaseModel):
    """One seeded invariant and where it was inserted."""

    model_config = ConfigDict(extra="forbid")

    plant_id: str
    type: str
    value: str
    document: str
    #: `base` or `revision`. The same document exists in two states for index freshness,
    #: and a plant that did not say which one it belonged to would make the stale value
    #: and the fresh value indistinguishable.
    state: str = "base"
    tenant: Optional[str] = None
    namespace: Optional[str] = None
    location: Optional[str] = None
    #: Other plants that must appear together with this one for the answer to be
    #: complete. Absence of a companion is an omission finding, not a hallucination.
    companions: list[str] = Field(default_factory=list)
    #: Which regeneration the collision guard accepted. Recorded so reproducing the
    #: battery from the seed needs no search (§3.2).
    attempt: int = 0


class Expectation(BaseModel):
    """What one check expects of one probe's answer."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str
    check: str
    #: Exact strings that must appear. Tier 1 when these are planted invariants.
    must_contain: list[str] = Field(default_factory=list)
    #: Exact strings that must not appear. The inverted form — the one that does not
    #: need a model, because absence is checkable and correctness is not (§3.1).
    must_not_contain: list[str] = Field(default_factory=list)
    #: The answer must cite at least one of these document identifiers.
    must_cite_any_of: list[str] = Field(default_factory=list)
    #: Fact/identifier pairs that must co-occur within one unit of text. A list because
    #: structural integrity needs the leaf beside its header *and* attribution needs one
    #: pairing per source document.
    adjacency: list[Adjacency] = Field(default_factory=list)
    #: Values belonging to the *other* side of a counterparty pair. Their presence is a
    #: swap — a distinct and more serious finding than an omission, because the system
    #: did not fail to answer, it answered with somebody else's data (§8.2 #5).
    swaps: list[str] = Field(default_factory=list)
    #: The target's own masking placeholders. One leaking into an answer is a third
    #: failure again: the re-hydration layer emitting its internal form.
    mask_tokens: list[str] = Field(default_factory=list)
    #: Classes of specific claim that would be fabricated here, by name — `figure`,
    #: `date`, `citation`. Abstention is scored by the presence of a claim of the shape
    #: requested, never by matching refusal language: *"I don't have that"* has a
    #: thousand phrasings and enumerating them is the trap this design avoids (§8.2 #8).
    shapes: list[str] = Field(default_factory=list)
    side_effect: Optional[SideEffect] = None
    pairing: Optional[Pairing] = None
    #: The tenant the probe was issued as, for scoping leakage checks.
    queried_as: Optional[str] = None
    #: The namespace the query was scoped to, where the target supports scoping. Null
    #: means it does not, and the routing check says so rather than implying otherwise.
    scoped_to: Optional[str] = None


class GroundTruth(BaseModel):
    """The manifest as a whole."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["ground_truth.v2"] = Field(
        default=GROUND_TRUTH_V2, alias="schema"
    )
    #: The seed that generated `plants`. Null only for a battery with no plants at all.
    seed: Optional[str] = None
    #: Where the seed came from, in words — the published demo seed, or one supplied for
    #: this run. A report whose plants came from a published seed cannot claim they were
    #: unguessable, and this is what stops it claiming that by omission.
    seed_source: Optional[str] = None
    plants: list[Plant] = Field(default_factory=list)
    guard: Optional[PlantGuard] = None
    expectations: list[Expectation]

    def for_check(self, check: str) -> dict[str, Expectation]:
        """Expectations for one check, keyed by probe id."""
        return {e.probe_id: e for e in self.expectations if e.check == check}

    def plant_for(self, plant_id: str) -> Optional[Plant]:
        return next((p for p in self.plants if p.plant_id == plant_id), None)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def load_ground_truth(path: str | Path) -> GroundTruth:
    p = Path(path)
    if not p.exists():
        raise InterchangeError(f"{p}: no such file.")
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InterchangeError(
            f"{p}: not valid JSON ({e.msg} at line {e.lineno}, column {e.colno})."
        ) from None
    if not isinstance(obj, dict):
        raise InterchangeError(f"{p}: expected a JSON object at the top level.")

    assert_schema(obj.get("schema"), GROUND_TRUTH_V2, where=str(p))

    try:
        gt = GroundTruth(**obj)
    except ValidationError as e:
        parts = [
            f"{'.'.join(str(x) for x in err['loc']) or '(document)'}: {err['msg']}"
            for err in e.errors()
        ]
        raise InterchangeError(f"{p}: {'; '.join(parts)}") from None

    seen: set[tuple[str, str]] = set()
    for e in gt.expectations:
        key = (e.probe_id, e.check)
        if key in seen:
            raise InterchangeError(
                f"{p}: two expectations for probe {e.probe_id!r} check {e.check!r}.\n"
                f"  One expectation per (probe_id, check) — otherwise which one the\n"
                f"  report was scored against depends on file order."
            )
        seen.add(key)

    planted: set[tuple[str, str]] = set()
    for plant in gt.plants:
        key = (plant.plant_id, plant.state)
        if key in planted:
            raise InterchangeError(
                f"{p}: two plants named {plant.plant_id!r} in state {plant.state!r}.\n"
                f"  Plant ids key the corpus to the findings; a duplicate makes it\n"
                f"  ambiguous which document a leaked token came from."
            )
        planted.add(key)

    return gt


def write_ground_truth(path: str | Path, gt: GroundTruth) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(gt.to_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
