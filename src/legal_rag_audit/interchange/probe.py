"""`probes.v2` — the probe file (V2_FULL_PLAN.md §6.2).

Handed to the target. Contains the questions and nothing else: no expected tokens, no
indication of which answer would be a finding. Expectations live in the withheld
ground-truth manifest (§3.6), because a probe file that carries them is an answer key.

`eligible_for` is the one field that does real work at scoring time. It is declared
here, before the run, and every denominator in the report derives from it — never from
what the results turned out to be (F39, §3.5 rule 3).

`phase` is v2's addition. Index freshness asks the same question before and after a
document is revised, and without a field saying which is which there is no way to tell
*"not yet indexed"* from *"never invalidated"* — different findings with different
severity (§8.2 #4). It sits in the probe file rather than in the withheld half because a
target running their own harness has to know when to apply the revision; what it does not
say is which value is stale and which is fresh.
"""

from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .jsonl import InterchangeError, read_records, write_records
from .versions import PROBES_V2, assert_schema

#: `positive` — a correct answer exists and the ground truth says what it contains.
#: `no_correct_answer` — nothing in the corpus supports an answer. Answering confidently
#: is the finding; refusing is the pass. Scoring these as if a right answer existed is
#: how a refusal gets counted as a failure.
Intent = Literal["positive", "no_correct_answer"]

#: `initial` — asked against the corpus as first uploaded.
#: `after_revision` — asked again once the revised documents have replaced their
#: originals and the declared wait has elapsed.
Phase = Literal["initial", "after_revision"]


class Probe(BaseModel):
    """One question, addressed to the target."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["probes.v2"] = Field(default=PROBES_V2, alias="schema")
    probe_id: str
    family: str
    intent: Intent
    text: str
    tenant: Optional[str] = None
    phase: Phase = "initial"
    #: Point-in-time probes (§9.2, F27) ask what the law said on a date. Null means the
    #: question is not time-qualified.
    as_at_date: Optional[str] = None
    #: Check names this probe can be scored against. A check may only count a probe in
    #: its denominator if it appears here.
    eligible_for: list[str] = Field(min_length=1)
    passes: int = Field(default=1, ge=1)

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def load_probes(path: str | Path) -> list[Probe]:
    """Read a probe file, refusing anything malformed or of an unknown version."""
    probes: list[Probe] = []
    seen_ids: set[str] = set()

    for lineno, obj in read_records(path):
        where = f"{path}:{lineno}"
        assert_schema(obj.get("schema"), PROBES_V2, where=where)
        try:
            probe = Probe(**obj)
        except ValidationError as e:
            raise InterchangeError(f"{where}: {_explain(e)}") from None
        if probe.probe_id in seen_ids:
            raise InterchangeError(
                f"{where}: duplicate probe_id {probe.probe_id!r}.\n"
                f"  Probe ids key the ground truth and the responses; a duplicate makes\n"
                f"  it ambiguous which expectation applies."
            )
        seen_ids.add(probe.probe_id)
        probes.append(probe)

    return probes


def write_probes(path: str | Path, probes: list[Probe]) -> None:
    write_records(path, [p.to_record() for p in probes])


def _explain(e: ValidationError) -> str:
    """Flatten a pydantic error into something a stranger can act on."""
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "(record)"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
