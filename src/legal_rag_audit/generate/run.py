"""`generate` — fire the battery at the target, write `responses.jsonl`.

This mode scores nothing. It asks questions, records what came back verbatim, and
stops. That separation is the point of §5.1: the target can run this, or replace it
entirely with their own tooling, and `score` cannot tell the difference. Anything this
module decided about whether an answer was *good* would be a decision the target had
no way to reproduce or contest.

Two rules it follows because the report depends on them:

* **A failed request is recorded as a failure, not as an answer.** A timeout produces a
  record with `error` set and an empty `answer`. Score reads that as NOT_CAPTURED. The
  alternative — an empty string that looks like the target said nothing — is how a
  network problem becomes a finding about somebody's product (NF9).
* **What could not be captured is declared.** The capture-notes header states whether
  citations and retrieved chunks were available at all, and lists the document
  identifiers the target issued at upload. Checks that need what is missing are named
  in the report rather than silently dropped (F40).
"""

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..authorisation import Authorisation, require
from ..config import AuditConfig
from ..corpus_loader import load_corpus, load_planted
from ..interchange import (
    CaptureNotes,
    Probe,
    Response,
    RetrievedChunk,
    load_probes,
    write_probes,
    write_responses,
)
from ..probes import build_probes, validate_battery
from ..transport import TargetClient

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """The run could not be set up. Aborts before any file is written (NF9)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class Generator:
    """Runs the battery once per pass and collects the raw results."""

    def __init__(
        self,
        config: AuditConfig,
        documents: list[dict[str, Any]],
        revisions: Optional[list[dict[str, Any]]] = None,
        passes: int = 1,
        skip_upload: bool = False,
        authorisation: Optional[Authorisation] = None,
    ):
        if passes < 1:
            raise GenerationError(f"passes must be at least 1, got {passes}")
        self.config = config
        #: Passed in already checked. The gate lives in `generate()` because it has to
        #: fire before a corpus is uploaded, and by the time this class exists the
        #: decision has been made — this only carries it into the response file.
        self.authorisation = authorisation
        self.documents = documents
        self.revisions = revisions or []
        self.passes = passes
        self.skip_upload = skip_upload
        self.run_id = uuid.uuid4().hex[:16]
        self.client = TargetClient(config.target)
        self.document_ids: list[str] = []
        #: Corpus document id -> the identifier the *target* answered with at upload.
        #: Kept beside `document_ids` rather than derived from it, because a replacement
        #: has to be addressed by the name the target chose: our `integration_fee_notice`
        #: is Vectara's `integration_fee_notice.txt`, and deleting the wrong string
        #: silently succeeds on an API that treats a miss as a no-op.
        self.issued_ids: dict[str, str] = {}
        #: Set once we know whether the target emits these at all, rather than guessed
        #: per record.
        self.saw_citations = False
        self.saw_chunks = False
        #: How long we actually waited between replacing the documents and asking again.
        #: Null when there was no revision phase — an absent wait and a zero wait are
        #: different facts and index freshness reads them differently (§8.2 #4).
        self.revision_wait: Optional[int] = None
        self.skipped_revision: Optional[str] = None

    async def run(self, probes: list[Probe]) -> tuple[list[Response], CaptureNotes]:
        initial = [p for p in probes if p.phase == "initial"]
        revised = [p for p in probes if p.phase == "after_revision"]

        try:
            await self._upload(self.documents, "corpus")
            responses = await self._ask_all(initial)
            if revised:
                responses += await self._revision_phase(revised)
        finally:
            await self.client.close()

        notes = CaptureNotes(
            record="capture_notes",
            citations_captured=self.saw_citations,
            retrieved_chunks_captured=self.saw_chunks,
            document_ids=self.document_ids or None,
            revision_wait_seconds=self.revision_wait,
            # §13 rule 3. It travels here rather than in the config hash because `score`
            # sees no config — on the artefact route it never even exists on our machine.
            # A report that names a cross-tenant leak and cannot say who authorised the
            # test for it is a report nobody should have produced.
            authorisation=self.authorisation,
            notes=" ".join(
                part
                for part in (
                    # `target.pseudonym`, never `target.name`. This string is inside the
                    # file the artefact route hands to someone else, so it is the worst
                    # place in the tool to put a vendor's name by default — and it was
                    # the only place the name appeared at all.
                    f"Produced by legal-rag-audit generate against "
                    f"{self.config.target.pseudonym!r}."
                    if self.config.target.pseudonym
                    else "Produced by legal-rag-audit generate.",
                    self.skipped_revision,
                )
                if part
            ),
        )
        return responses, notes

    async def _ask_all(self, probes: list[Probe]) -> list[Response]:
        responses: list[Response] = []
        for pass_index in range(1, self.passes + 1):
            if self.passes > 1:
                logger.info(f"Pass {pass_index} of {self.passes}")
            for probe in probes:
                responses.append(await self._ask(probe, pass_index))
        return responses

    async def _revision_phase(self, probes: list[Probe]) -> list[Response]:
        """Replace the revised documents, wait, then ask the second-phase questions.

        Skipped loudly rather than quietly. A run that could not revise has not tested
        index freshness, and the probes are left unasked so scoring reports them as
        NOT_CAPTURED — which is true — instead of asking them against an unchanged corpus
        and reporting the unchanged answer as a stale index (NF9).
        """
        if not self.revisions:
            self.skipped_revision = (
                "No revision phase: the corpus carries no revised documents, so the "
                "second-phase probes were not asked."
            )
        elif self.skip_upload:
            self.skipped_revision = (
                "No revision phase: uploads were skipped, so the revised documents "
                "could not replace the originals and the second-phase probes were not "
                "asked."
            )
        if self.skipped_revision:
            logger.warning(self.skipped_revision)
            return []

        try:
            await self._clear_for_replacement(self.revisions)
            await self._upload(self.revisions, "revision")
        except GenerationError as e:
            # A failed *revision* upload is not a failed run. The base corpus is in the
            # index and the first-phase probes have already been answered against it, so
            # aborting here would throw away complete evidence to report the absence of
            # one check — and the absence is reportable on its own (F40). The two
            # branches above skip loudly for the same reason; this is the third way the
            # phase can not happen, and it was the only one that discarded the run.
            #
            # Base-upload failures still abort, and that asymmetry is the point: without
            # the base corpus every check is scored against documents the target may not
            # hold, which is not partial evidence but wrong evidence.
            self.skipped_revision = (
                f"No revision phase: the revised documents could not be uploaded, so "
                f"the second-phase probes were not asked and index freshness is "
                f"NOT_CAPTURED rather than passing or failing.\n{e}"
            )
            logger.warning(self.skipped_revision)
            return []

        wait = self.config.corpus.revision_wait_seconds
        logger.info(
            f"Revision uploaded. Waiting {wait}s before re-asking, so a stale answer "
            f"means an index that did not invalidate rather than one still working."
        )
        if wait:
            await asyncio.sleep(wait)
        self.revision_wait = wait

        return await self._ask_all(probes)

    async def _clear_for_replacement(self, documents: list[dict[str, Any]]) -> None:
        """Free the identifiers a revision is about to reuse, where the config allows it.

        **This deletes documents from the target's index**, which nothing else in this
        tool does, so read the three conditions rather than the summary:

        1. `endpoints.delete` is configured. Absent by default; without it this is a
           no-op and the revision phase proceeds exactly as it did before, failing loudly
           on a create-only API instead of silently destroying anything.
        2. Uploads are enabled. `--skip-upload` means the target's copy of the corpus is
           theirs and not ours to replace, and the revision phase is already skipped in
           that case.
        3. The identifier belongs to a document *this run uploaded*. `self.revisions`
           comes from the planted corpus we wrote, and the deletion is by that identifier
           alone — there is no query, no pattern and no way for this to reach a document
           the run did not put there.

        Why it exists: §8.2 #4 tells "not yet indexed" from "never invalidated" by
        replacing a document mid-run and asking again. An ingest API that refuses
        duplicate identifiers cannot be made to replace anything by uploading twice — it
        answers 409 — so on those targets the check is not awkward but impossible.

        A failure here is not fatal and deliberately not caught: it propagates to the
        caller, which turns the whole revision phase into a loud skip. A target that
        would not let us free the identifier is a target where index freshness is
        NOT_CAPTURED, and that is a true statement about the run.
        """
        if not documents or self.skip_upload:
            return
        if self.config.target.endpoints.delete is None:
            logger.info(
                "No `endpoints.delete`: the revision will be uploaded over the original. "
                "On a target whose ingest API refuses duplicate identifiers this fails, "
                "and index freshness is then reported as NOT_CAPTURED rather than passing."
            )
            return

        for doc in documents:
            # The identifier the target answered with at upload, not ours. Falling back
            # to the filename rather than to `doc["id"]`: a file-upload API almost always
            # keys on the filename, and our id is that with the extension stripped.
            identifier = self.issued_ids.get(doc["id"], doc["filename"])
            logger.info(
                f"Deleting {identifier} before replacing it — the identifier is reused "
                f"by the revised document, and this target's ingest is create-only."
            )
            await self.client.delete_document(identifier)

    async def _upload(self, documents: list[dict[str, Any]], label: str) -> None:
        if not documents:
            # Existing-corpus mode. Distinguished from `--skip-upload` in the log because
            # they are different facts: one is a run that had nothing to send, the other
            # is a run that chose not to send what it had.
            logger.info(
                f"{label.capitalize()}: no documents — this battery scores against the "
                f"target's own index and uploads nothing (F25)."
            )
            return

        logger.info(f"{label.capitalize()}: {len(documents)} documents.")

        if not self.skip_upload and self.config.target.endpoints.upload is None:
            raise GenerationError(
                f"{len(documents)} documents to upload and no `endpoints.upload` in the "
                f"config.\n"
                f"  Three ways out, and they mean different things:\n"
                f"    corpus.mode: existing   probe the target's own index; nothing is\n"
                f"                            uploaded and no upload endpoint is needed\n"
                f"    --skip-upload           the target already holds this corpus\n"
                f"    endpoints.upload: ...   send it\n"
                f"  Aborting rather than asking questions about documents the target\n"
                f"  may not have."
            )

        if self.skip_upload:
            logger.info("Skipping upload; the target is assumed to hold the corpus.")
            # No identifiers were issued to us, so citation integrity has no set to
            # test membership against. Left empty rather than filled with our own
            # filenames, which the target never agreed to use.
            return

        for doc in documents:
            try:
                resp = await self.client.upload_document(
                    doc["filename"], doc["content"], metadata={"id": doc["id"]}
                )
            except Exception as e:
                raise GenerationError(
                    f"Upload of {doc['filename']} failed: {e}\n"
                    f"  Every check depends on the target holding the corpus. Aborting\n"
                    f"  rather than producing a response file scored against documents\n"
                    f"  the target may not have."
                ) from None

            if isinstance(resp, dict) and (
                resp.get("status") == "error"
                or resp.get("success") is False
                or "error" in resp
            ):
                raise GenerationError(
                    f"Upload of {doc['filename']} returned a success status with an "
                    f"error body: {resp}\n"
                    f"  A 200 that did not store the document is the failure mode this\n"
                    f"  check exists to catch."
                )

            issued = resp.get("id") if isinstance(resp, dict) else None
            identifier = str(issued) if issued else doc["id"]
            self.issued_ids[doc["id"]] = identifier
            # A revised document replaces its original, so its identifier is already in
            # the manifest. Appending it again would put the same document into the set
            # citation integrity tests membership against twice.
            if identifier not in self.document_ids:
                self.document_ids.append(identifier)

        logger.info(f"Uploaded {len(documents)} documents ({label}).")

    async def _ask(self, probe: Probe, pass_index: int) -> Response:
        started = _now()
        t0 = time.monotonic()
        try:
            result = await self.client.chat(probe.text)
        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.error(f"{probe.probe_id}: request failed: {e}")
            return Response(
                run_id=self.run_id,
                probe_id=probe.probe_id,
                pass_index=pass_index,
                query=probe.text,
                tenant=probe.tenant,
                answer="",
                total_ms=elapsed,
                http_status=_status_of(e),
                error=f"{type(e).__name__}: {e}",
                started_at=started,
            )

        total_ms = int((time.monotonic() - t0) * 1000)
        answer = result.get("answer", "") or ""
        raw = result.get("raw")

        citations = result.get("citations")
        if isinstance(citations, list):
            self.saw_citations = True
            citations = [str(c) for c in citations]
        else:
            citations = None

        chunks = await self._retrieve_chunks(probe.text, raw)
        if chunks is not None:
            self.saw_chunks = True

        return Response(
            run_id=self.run_id,
            probe_id=probe.probe_id,
            pass_index=pass_index,
            query=probe.text,
            tenant=probe.tenant,
            answer=answer,
            citations=citations,
            retrieved_chunks=chunks,
            # TODO(D): the transport reads the full body before returning, so time to
            # first byte is not observable here. Recording total under both names —
            # which v1 did — makes the TTFB-to-total gap in evaluator 15 compare a
            # number with itself. Left null so the check reports it as not captured
            # rather than silently scoring a vacuous comparison.
            ttfb_ms=None,
            total_ms=total_ms,
            http_status=200,
            error=None,
            started_at=started,
            raw_response=raw if raw else None,
        )

    async def _retrieve_chunks(
        self, query: str, raw: Any
    ) -> Optional[list[RetrievedChunk]]:
        """Chunks from the dedicated retrieval endpoint, or from the chat body.

        Returns None — not `[]` — when the target exposes no way to see them. The
        difference decides whether retrieval relevance is scored against an empty
        retrieval or reported as not captured.
        """
        endpoint = self.config.target.endpoints.retrieval
        if endpoint is not None:
            try:
                url, method, headers, kwargs = self.client._prepare_request(
                    endpoint,
                    default_payload={"query": query},
                    variables={"QUERY": query},
                )
                r = await self.client.client.request(
                    method, url, headers=headers, **kwargs
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    return [
                        RetrievedChunk(
                            text=item.get("content", "") or item.get("text", ""),
                            doc_id=item.get("doc_id") or item.get("id"),
                        )
                        for item in data
                        if isinstance(item, dict)
                    ]
                logger.warning(
                    f"Retrieval endpoint returned {r.status_code}; "
                    f"chunks not captured for this probe."
                )
                return None
            except Exception as e:
                logger.warning(f"Retrieval endpoint failed: {e}")
                return None

        found = _chunks_in_body(raw)
        return found

    async def close(self) -> None:
        await self.client.close()


def _status_of(exc: Exception) -> Optional[int]:
    """The HTTP status behind an exception, when there was one."""
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _chunks_in_body(raw: Any) -> Optional[list[RetrievedChunk]]:
    """Chunks embedded in the chat response, if the target puts them there."""
    candidates: list[Any] = []
    if isinstance(raw, dict):
        candidates = raw.get("chunks") or []
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "chunks" in item:
                candidates.extend(item["chunks"] or [])
    else:
        return None

    if not candidates:
        return None

    chunks = []
    for item in candidates:
        if isinstance(item, dict):
            chunks.append(
                RetrievedChunk(
                    text=item.get("content", "") or item.get("text", ""),
                    doc_id=item.get("doc_id") or item.get("id"),
                )
            )
        elif isinstance(item, str):
            chunks.append(RetrievedChunk(text=item))
    return chunks or None


DEFAULT_PLANTED_PATH = "./planted-corpus"

#: What `resolve_corpus` reports as the corpus location in existing mode. Not a path,
#: because there is not one: the corpus is whatever the target already holds, and the run
#: manifest should say that rather than name a directory nobody used.
EXISTING_INDEX = "the target's own index — nothing was uploaded"


def resolve_corpus(
    config: AuditConfig, corpus_dir: Optional[str] = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """The documents to upload, the ones that replace them, and where they came from.

    A planted corpus is written to disk and read back rather than passed in memory, so
    the tree `hash` sealed and the tree that goes to the target are the same bytes. Two
    objects nobody compared is how a pre-commitment quietly stops meaning anything.
    """
    if corpus_dir:
        documents, revisions = load_planted(corpus_dir)
        return documents, revisions, corpus_dir

    if config.corpus.mode == "existing":
        # Nothing to upload, and no path to read (F25). §9.1's second configuration
        # probes the target's own live index, so the documents are theirs and we never
        # see them — which is exactly what makes its findings impossible to dismiss as
        # synthetic, and what lets the whole half run against `chat` alone.
        #
        # Until Phase G this branch read a local directory and uploaded it, which was
        # planted mode wearing the other name: it still needed an upload endpoint, so
        # the one objection existing mode exists to defeat still applied.
        if config.corpus.path:
            logger.warning(
                f"corpus.path is set to {config.corpus.path!r} and existing mode does "
                f"not read it. The target's own index is the corpus; nothing is "
                f"uploaded and no local documents are involved."
            )
        return [], [], EXISTING_INDEX

    from ..corpora import load as load_library_corpus
    from ..plants import plant, write_corpus

    root = os.path.join(config.corpus.path or DEFAULT_PLANTED_PATH, "corpus")
    corpus = plant(config.corpus.seed, load_library_corpus(config.corpus.library))
    written = write_corpus(root, corpus)
    logger.info(
        f"Planted {written['base']} documents and {written['revision']} revisions into "
        f"{root} from {corpus.seed_source}, using corpus {corpus.source.label}."
    )
    documents, revisions = load_planted(root)
    return documents, revisions, root


def generate(
    config: AuditConfig,
    responses_path: str,
    probes_path: Optional[str] = None,
    passes: int = 1,
    skip_upload: bool = False,
    corpus_dir: Optional[str] = None,
    probes_in: Optional[str] = None,
    production_ack: bool = False,
) -> int:
    """Run the battery and write the response file. Returns the record count.

    `corpus_dir` and `probes_in` are the engagement path: the target is given a sealed
    corpus and a sealed probe file and runs against exactly those. They travel together
    because a probe file scores against the invariants of the corpus it was built with —
    replanting from a seed the target does not hold would produce different values and
    every Tier 1 check would fail for a reason that has nothing to do with their system.
    """
    if corpus_dir and not probes_in:
        raise GenerationError(
            "--corpus was given without --probes-in.\n"
            "  A planted corpus and its probe file are one artefact: the probes score\n"
            "  against invariants minted from the seed that produced those documents.\n"
            "  Building fresh probes here would mint different values, and every Tier 1\n"
            "  check would fail for a reason that has nothing to do with the target.\n"
            "  Pass the probes.jsonl written alongside the corpus by `plant`."
        )

    documents, revisions, resolved = resolve_corpus(config, corpus_dir)

    if probes_in:
        probes = load_probes(probes_in)
        logger.info(f"Probe file read from {probes_in} ({len(probes)} probes).")
    else:
        validate_battery()
        probes = build_probes(passes=passes)

    if probes_path:
        write_probes(probes_path, probes)
        logger.info(f"Probe file written to {probes_path} ({len(probes)} probes).")

    # §13, before the first request rather than after it. The gate reads the probe file's
    # own families, so it holds on the artefact route too: a battery handed over as
    # probes.jsonl is classified from what it asks, not from what a config claims it is.
    authorisation = require(
        config.authorisation,
        (p.family for p in probes),
        uploads=bool(documents) and not skip_upload,
        production_ack=production_ack,
    )
    if authorisation is not None:
        logger.info(
            f"Authorised by {authorisation.authorised_by} on "
            f"{authorisation.authorised_on.isoformat()} "
            f"({authorisation.environment}); recorded in the report verbatim."
        )

    generator = Generator(
        config,
        documents=documents,
        revisions=revisions,
        passes=passes,
        skip_upload=skip_upload,
        authorisation=authorisation,
    )
    responses, notes = asyncio.run(generator.run(probes))
    write_responses(responses_path, responses, capture_notes=notes)

    failed = sum(1 for r in responses if not r.usable)
    logger.info(
        f"Wrote {len(responses)} records to {responses_path} "
        f"({len(responses) - failed} with answers, {failed} with transport errors)."
    )
    if failed:
        logger.warning(
            f"{failed} of {len(responses)} probes did not return an answer. Those "
            f"records are NOT_CAPTURED at scoring time; they are not findings."
        )
    return len(responses)
