"""`handover.v1` — the pre-commitment record (V2_FULL_PLAN.md §3.6, F38).

Written by `legal-rag-audit hash` **before any response exists**, and given to the
client at handover along with the corpus and the probe file. It says: these are the
exact bytes of the corpus you are about to index, these are the questions, and this
is the digest of the answer key we are not showing you yet.

The step that makes it worth anything comes later. `score --handover handover.json`
recomputes the digests and refuses to run if the ground truth it was given is not the
one that was committed to. Without that, the record is a number in a document nobody
checks; with it, the tool cannot produce a report from a key that was edited after
the responses came back.

Direction of protection, restated because it reads backwards to most people: this
constrains **us** more than it constrains the target. The accusation it answers is
*"you decided what counted as a failure after you saw the failure"*, and that
accusation is otherwise unanswerable and voids every finding in the report.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .jsonl import InterchangeError
from .versions import HANDOVER_V1, assert_schema


class HashedArtefact(BaseModel):
    """One digest, with everything needed to recompute it independently."""

    model_config = ConfigDict(extra="forbid")

    #: The path as it was given to `hash`. A label for the reader, not an identity —
    #: the artefact travels and will land somewhere else on their machine.
    path: str
    #: `file` or `tree`. The two are hashed differently and checking one with the
    #: other's recipe produces a mismatch that looks like tampering.
    kind: Literal["file", "tree"]
    digest: str
    #: Files covered, for a tree. A digest over an empty directory is a valid digest
    #: and a useless commitment, so the count is on the page.
    files: Optional[int] = None
    #: The recipe in full, so verification needs standard tools and not this package.
    recipe: str


class Handover(BaseModel):
    """What was committed to, when, and by which build."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["handover.v1"] = Field(default=HANDOVER_V1, alias="schema")
    #: UTC, ISO 8601. The date is the substance of a pre-commitment, not metadata.
    created: str
    tool_version: str
    tool_commit_sha: Optional[str] = None
    corpus: Optional[HashedArtefact] = None
    probes: Optional[HashedArtefact] = None
    ground_truth: Optional[HashedArtefact] = None
    #: Free text for the engagement — who received this, and when the key is due.
    note: Optional[str] = None

    def artefacts(self) -> dict[str, HashedArtefact]:
        return {
            name: value
            for name, value in (
                ("corpus", self.corpus),
                ("probes", self.probes),
                ("ground_truth", self.ground_truth),
            )
            if value is not None
        }

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_handover(path: str | Path) -> Handover:
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

    assert_schema(obj.get("schema"), HANDOVER_V1, where=str(p))

    try:
        return Handover(**obj)
    except ValidationError as e:
        parts = [
            f"{'.'.join(str(x) for x in err['loc']) or '(document)'}: {err['msg']}"
            for err in e.errors()
        ]
        raise InterchangeError(f"{p}: {'; '.join(parts)}") from None


def write_handover(path: str | Path, record: Handover) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(record.to_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
