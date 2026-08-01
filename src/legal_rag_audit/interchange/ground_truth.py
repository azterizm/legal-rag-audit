"""`ground_truth.v1` — the withheld manifest (V2_FULL_PLAN.md §6.4, F26).

Everything a probe file deliberately does not say: what a correct answer contains, what
it must never contain, and which document it has to be attributed to. Handed over
**hashed, not disclosed**, before the run (§3.6). Publishing the hash first is what
makes the expectations pre-committed rather than fitted to what came back.

Two halves, arriving in different phases:

* `expectations` — one per `(probe_id, check)`. Built in Phase B, because `score`
  cannot exist without it.
* `plants` — seeded, collision-guarded invariants inserted into the corpus. Phase D.
  Empty until then, and `seed` is null while it is: the demo corpus carries fixed
  facts, and calling a fixed fact a plant would misdescribe how it was produced.
"""

import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .jsonl import InterchangeError
from .versions import GROUND_TRUTH_V1, assert_schema


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


class Plant(BaseModel):
    """One seeded invariant and where it was inserted. Phase D populates this."""

    model_config = ConfigDict(extra="forbid")

    plant_id: str
    type: str
    value: str
    document: str
    tenant: Optional[str] = None
    location: Optional[str] = None
    #: Other plants that must appear together with this one for the answer to be
    #: complete. Absence of a companion is an omission finding, not a hallucination.
    companions: list[str] = Field(default_factory=list)


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
    adjacency: Optional[Adjacency] = None
    #: The tenant the probe was issued as, for scoping leakage checks.
    queried_as: Optional[str] = None
    #: Arguments the Phase B evaluators still take in their own shapes — PII pairs,
    #: fact/source tuples, the baseline/contradictory probe pairing for latency.
    #: Phase D rewrites evaluators 4–14 to the §8.2 recipes, at which point these fold
    #: into the fields above and this goes away. Named so it cannot be mistaken for
    #: part of the durable contract.
    legacy_params: dict[str, Any] = Field(default_factory=dict)


class GroundTruth(BaseModel):
    """The manifest as a whole."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["ground_truth.v1"] = Field(
        default=GROUND_TRUTH_V1, alias="schema"
    )
    #: The seed that generated `plants`. Null while there are none (Phase D).
    seed: Optional[str] = None
    plants: list[Plant] = Field(default_factory=list)
    expectations: list[Expectation]

    def for_check(self, check: str) -> dict[str, Expectation]:
        """Expectations for one check, keyed by probe id."""
        return {e.probe_id: e for e in self.expectations if e.check == check}

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

    assert_schema(obj.get("schema"), GROUND_TRUTH_V1, where=str(p))

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

    return gt


def write_ground_truth(path: str | Path, gt: GroundTruth) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(gt.to_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
