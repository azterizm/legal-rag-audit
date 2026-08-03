"""`responses.v2` — the interchange format (V2_FULL_PLAN.md §6.3, F19, F35).

The whole low-friction engagement rests on this file. A target may produce it with our
`generate` mode, with their own evaluation harness, or with thirty lines of curl and
jq — `score` cannot tell the difference and does not need to. Custody of the evidence
stays with them, which is what makes a finding hard to dismiss as *"your harness
prompted it wrong"*.

Because strangers write this file, two rules govern the models below:

* **Absence is recorded, never inferred.** `citations: null` means *we did not capture
  citations*; `citations: []` means *the target returned none*. Those are different
  facts and the report says which one it had. Collapsing them is how "no citations
  captured" becomes "cited nothing", which is a finding we would have to retract.
* **A transport failure is not a result.** A record with `error` set is `NOT_CAPTURED`
  for every check. An empty answer caused by a 502 is a setup problem (NF9); scoring it
  as a hallucination would be inventing a finding out of our own plumbing.
"""

from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .jsonl import InterchangeError, read_records, write_records
from .versions import RESPONSES_V2, assert_schema


class RetrievedChunk(BaseModel):
    """One chunk the target's retriever returned for this query.

    Extra keys are allowed: chunk metadata is the target's shape, not ours, and
    discarding their scores or offsets would make the evidence bundle less useful than
    the raw file they already have.
    """

    model_config = ConfigDict(extra="allow")

    text: str
    doc_id: Optional[str] = None


class CaptureNotes(BaseModel):
    """Optional first line of the file, declaring what the producer could capture.

    Without it, an absent field is ambiguous — we cannot tell "the target emits no
    citations" from "our script did not record them". With it, that ambiguity is
    resolved by the person who actually knows. Every check it disables is named in the
    report rather than quietly dropped.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["responses.v2"] = Field(default=RESPONSES_V2, alias="schema")
    record: Literal["capture_notes"]
    citations_captured: bool
    retrieved_chunks_captured: bool
    #: Document identifiers the target assigned to the uploaded corpus.
    #:
    #: Citation integrity is set membership — is each returned identifier one the
    #: target itself issued? — so without this list there is no set to test against and
    #: the check is NOT_CAPTURED. It is not optional detail: a target that returns no
    #: identifiers on upload cannot have its citations checked at all, which §7.1 lists
    #: as a condition `validate` exists to catch before the run rather than after it.
    document_ids: Optional[list[str]] = None
    #: Seconds waited between replacing a document and asking the same question again.
    #:
    #: v2's addition, and index freshness cannot be reported honestly without it. A
    #: superseded value coming back after two seconds is a system that has not finished
    #: indexing; after ten minutes it is a cache that never invalidates. Those are
    #: different findings with different severity, and only the elapsed time separates
    #: them (§8.2 #4). Null where the run had no revision phase.
    revision_wait_seconds: Optional[int] = None
    #: Free text. Goes into the run manifest verbatim.
    notes: Optional[str] = None

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class Response(BaseModel):
    """One `(probe_id, pass_index)` result."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["responses.v2"] = Field(default=RESPONSES_V2, alias="schema")
    #: Opaque. Ties a file to a run manifest; we never parse it.
    run_id: str
    probe_id: str
    #: 1-based. A file with one pass per probe scores fine and produces no variance
    #: findings, which the report states rather than leaving to be assumed.
    pass_index: int = Field(default=1, ge=1)
    #: The text actually sent. Recorded so a report can be checked against what was
    #: asked, not against what the probe file said should be asked.
    query: str
    tenant: Optional[str] = None
    #: Verbatim response text. Truncation invalidates Tier 1 — an exact-match check
    #: against a shortened answer measures the truncation.
    answer: str
    #: `null` = not captured. `[]` = captured, target returned none.
    citations: Optional[list[str]] = None
    #: `null` = not captured. Absence disables retrieval relevance and reduces that
    #: check's eligible denominator, which the report states.
    retrieved_chunks: Optional[list[RetrievedChunk]] = None
    ttfb_ms: Optional[int] = None
    total_ms: Optional[int] = None
    http_status: Optional[int] = None
    #: Non-null means this record carries no result. Every check reads it as
    #: NOT_CAPTURED; none reads it as a failure.
    error: Optional[str] = None
    started_at: Optional[str] = None
    #: Anything the producer wants preserved that the schema has no field for.
    raw_response: Optional[Any] = None

    @property
    def usable(self) -> bool:
        """False when this record carries a transport failure rather than an answer."""
        return self.error is None

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class ResponseFile(BaseModel):
    """A parsed response file: the optional header, plus the records."""

    model_config = ConfigDict(extra="forbid")

    capture_notes: Optional[CaptureNotes] = None
    responses: list[Response]

    def citations_captured(self) -> Optional[bool]:
        """Whether citations were captured, or None if nothing in the file says.

        Declared header first; otherwise inferred from whether any record carries a
        non-null `citations`. The inference is reported as an inference — a file where
        every record happens to have `null` is indistinguishable from one where the
        producer never looked, and the report must not claim to know which.
        """
        if self.capture_notes is not None:
            return self.capture_notes.citations_captured
        if any(r.citations is not None for r in self.responses):
            return True
        return None

    def retrieved_chunks_captured(self) -> Optional[bool]:
        if self.capture_notes is not None:
            return self.capture_notes.retrieved_chunks_captured
        if any(r.retrieved_chunks is not None for r in self.responses):
            return True
        return None


def load_responses(path: str | Path) -> ResponseFile:
    """Read a response file, refusing anything malformed or of an unknown version."""
    notes: Optional[CaptureNotes] = None
    responses: list[Response] = []
    seen: set[tuple[str, int]] = set()

    for index, (lineno, obj) in enumerate(read_records(path)):
        where = f"{path}:{lineno}"
        assert_schema(obj.get("schema"), RESPONSES_V2, where=where)

        # `record` is a discriminator, not data. Response lines omit it (§6.3), so the
        # default is "response" and an explicit one is accepted and dropped.
        obj = dict(obj)
        kind = obj.pop("record", "response")
        if kind == "capture_notes":
            obj["record"] = kind
            if index != 0:
                raise InterchangeError(
                    f"{where}: capture_notes must be the first record in the file.\n"
                    f"  It describes the whole file, so it cannot appear after records\n"
                    f"  it is meant to qualify."
                )
            try:
                notes = CaptureNotes(**obj)
            except ValidationError as e:
                raise InterchangeError(f"{where}: {_explain(e)}") from None
            continue

        if kind != "response":
            raise InterchangeError(
                f"{where}: unknown record type {kind!r}. "
                f"Expected \"response\" (the default) or \"capture_notes\"."
            )

        try:
            response = Response(**obj)
        except ValidationError as e:
            raise InterchangeError(f"{where}: {_explain(e)}") from None

        key = (response.probe_id, response.pass_index)
        if key in seen:
            raise InterchangeError(
                f"{where}: duplicate record for probe {response.probe_id!r} "
                f"pass {response.pass_index}.\n"
                f"  One record per (probe_id, pass_index). Repeated runs of the same\n"
                f"  probe are separate passes — increment pass_index."
            )
        seen.add(key)
        responses.append(response)

    if not responses:
        raise InterchangeError(
            f"{path}: contains a capture_notes header but no responses."
        )

    return ResponseFile(capture_notes=notes, responses=responses)


def write_responses(
    path: str | Path,
    responses: list[Response],
    capture_notes: Optional[CaptureNotes] = None,
) -> None:
    records = [capture_notes.to_record()] if capture_notes is not None else []
    records.extend(r.to_record() for r in responses)
    write_records(path, records)


def _explain(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "(record)"
        if err["type"] == "extra_forbidden":
            parts.append(
                f"{loc}: unknown field. Fields outside the schema belong under "
                f"`raw_response`, which is preserved verbatim"
            )
        else:
            parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
