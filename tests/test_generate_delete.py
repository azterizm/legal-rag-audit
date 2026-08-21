"""The one destructive call, and the fence around it.

`endpoints.delete` exists because §8.2 #4 replaces a document mid-run to tell "not yet
indexed" from "never invalidated", and an ingest API that refuses duplicate identifiers
cannot be made to replace anything by uploading twice — Vectara's `upload_file` answers
409. Without it the check is impossible on those targets rather than merely awkward.

Everything else in this tool only ever adds to a target's index. That makes this the
capability worth over-testing: the failure mode is not a wrong finding, it is somebody
else's data gone. Four properties, and the first three are the fence:

1. It never fires without `endpoints.delete` in the config.
2. It never fires outside the revision phase, and never with `--skip-upload`.
3. It only ever names an identifier this run uploaded.
4. When it fails, the run does not die — the revision phase becomes a loud skip and
   index freshness is NOT_CAPTURED.
"""

from typing import Any, Optional

import asyncio

import pytest

from legal_rag_audit.config import AuditConfig
from legal_rag_audit.generate import run as run_module
from legal_rag_audit.generate.run import Generator, GenerationError
from legal_rag_audit.interchange.probe import Probe

BASE = {
    "target": {
        "name": "example",
        "endpoints": {
            "chat": "https://example.invalid/chat",
            "upload": "https://example.invalid/upload",
        },
    }
}
DELETE_URL = "https://example.invalid/docs/{{DOCUMENT_ID}}"


def config(*, delete: Optional[str] = None) -> AuditConfig:
    endpoints = dict(BASE["target"]["endpoints"])
    if delete:
        endpoints["delete"] = delete
    return AuditConfig(
        **{
            "target": {**BASE["target"], "endpoints": endpoints},
            # The default is 60 seconds, and it is right for a real run: a stale answer
            # two seconds after a replacement is an index still working, not one that
            # never invalidates. Nothing here talks to an index, so the wait is dead time
            # multiplied by every test that reaches the revision phase.
            "corpus": {"revision_wait_seconds": 0},
        }
    )


def document(name: str) -> dict[str, Any]:
    return {"id": name, "filename": f"{name}.txt", "content": f"body of {name}"}


class RecordingClient:
    """Stands in for `TargetClient`, and remembers what it was told to destroy."""

    def __init__(self, *, upload_error: Optional[Exception] = None) -> None:
        self.deleted: list[str] = []
        self.uploaded: list[str] = []
        self.upload_error = upload_error

    async def upload_document(self, filename, content, metadata=None):
        if self.upload_error is not None:
            raise self.upload_error
        self.uploaded.append(filename)
        # Most file-upload APIs key on the filename, and the identifier the target
        # answers with is the one a later delete has to name.
        return {"id": filename}

    async def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)

    async def chat(self, text: str, attachments=None):
        return {"answer": "an answer", "citations": [], "raw": {}}

    async def close(self) -> None:
        pass


def generator(cfg: AuditConfig, client: RecordingClient, **kwargs) -> Generator:
    gen = Generator(
        cfg,
        documents=[document("alpha"), document("fee_notice")],
        revisions=[document("fee_notice")],
        **kwargs,
    )
    gen.client = client
    return gen


PROBES = [
    Probe(
        probe_id="p-1",
        family="disambiguation",
        intent="positive",
        text="q?",
        eligible_for=["disambiguation"],
    ),
    Probe(
        probe_id="p-2",
        family="index_freshness",
        intent="positive",
        text="q?",
        eligible_for=["index_freshness"],
        phase="after_revision",
    ),
]


def test_nothing_is_deleted_when_no_delete_endpoint_is_configured() -> None:
    """The default. A config that never mentions deletion must never cause one."""
    client = RecordingClient()
    gen = generator(config(), client)
    asyncio.run(gen.run(PROBES))
    assert client.deleted == []


def test_the_revision_document_is_deleted_before_it_is_replaced() -> None:
    client = RecordingClient()
    gen = generator(config(delete=DELETE_URL), client)
    asyncio.run(gen.run(PROBES))
    assert client.deleted == ["fee_notice.txt"]


def test_only_the_revised_document_is_deleted() -> None:
    """The base corpus is not ours to remove, and `alpha` has no revision.

    A delete loop over the wrong collection is the mistake that would empty a target's
    index while every test about *whether* deletion happens still passed.
    """
    client = RecordingClient()
    gen = generator(config(delete=DELETE_URL), client)
    asyncio.run(gen.run(PROBES))
    assert "alpha.txt" not in client.deleted
    assert len(client.deleted) == 1


def test_it_names_the_identifier_the_target_issued() -> None:
    """Not ours. `fee_notice` is our id; `fee_notice.txt` is what the target answered.

    Deleting the wrong string succeeds silently on any API that treats a miss as a no-op,
    and the run would then fail at upload with a 409 that looks like the original defect.
    """
    client = RecordingClient()
    gen = generator(config(delete=DELETE_URL), client)
    asyncio.run(gen.run(PROBES))
    assert client.deleted == ["fee_notice.txt"] != ["fee_notice"]


def test_skip_upload_deletes_nothing() -> None:
    """The target's copy of the corpus is theirs, not ours to replace."""
    client = RecordingClient()
    gen = generator(config(delete=DELETE_URL), client, skip_upload=True)
    asyncio.run(gen.run(PROBES))
    assert client.deleted == []
    assert gen.skipped_revision and "uploads were skipped" in gen.skipped_revision


def test_a_corpus_with_no_revision_deletes_nothing() -> None:
    client = RecordingClient()
    gen = Generator(config(delete=DELETE_URL), documents=[document("alpha")])
    gen.client = client
    asyncio.run(gen.run(PROBES))
    assert client.deleted == []


class TestAFailedRevisionDoesNotDiscardTheRun:
    """Defect found by the Vectara dry run: a 409 threw away 18 answered probes.

    The base corpus was in the index and the first-phase probes had been answered against
    it. Aborting reported the absence of one check by destroying the evidence for
    eighteen, when the absence is reportable on its own (F40).
    """

    def test_the_first_phase_answers_survive(self) -> None:
        client = RecordingClient()
        gen = generator(config(), client)
        # Fails only once the base upload has happened, which is the shape of the real
        # defect: a create-only ingest accepts the corpus and refuses the replacement.
        original = client.upload_document

        async def fail_on_revision(filename, content, metadata=None):
            if gen.skipped_revision is None and filename in client.uploaded:
                raise RuntimeError("409 Conflict")
            return await original(filename, content, metadata)

        client.upload_document = fail_on_revision
        responses, _ = asyncio.run(gen.run(PROBES))

        assert [r.probe_id for r in responses] == ["p-1"]
        assert gen.skipped_revision and "NOT_CAPTURED" in gen.skipped_revision

    def test_a_failed_base_upload_still_aborts(self) -> None:
        """The asymmetry is the point.

        Without the base corpus every check would be scored against documents the target
        may not hold — not partial evidence but wrong evidence.
        """
        from legal_rag_audit.generate.run import GenerationError

        client = RecordingClient(upload_error=RuntimeError("connection refused"))
        gen = generator(config(), client)
        with pytest.raises(GenerationError):
            asyncio.run(gen.run(PROBES))


class TestTheBatteryCanBePaced:
    """Pacing exists because an unpaced run measured nothing and spent a stranger's quota.

    A 22-probe three-pass battery went out in 111 seconds at a median of one second
    apart. The endpoint answered with one read timeout, six `403`s and fifty-nine
    `429`s — 66 records, 0 answers. Nothing was mis-scored, because every record was
    written as a transport error, but the run was worthless and the footprint was not.
    """

    def _timed(self, monkeypatch):
        """Record what the runner sleeps for, without actually waiting."""
        slept: list[float] = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(run_module.asyncio, "sleep", fake_sleep)
        return slept

    def test_the_delay_falls_between_requests_not_before_the_first(self, monkeypatch):
        slept = self._timed(monkeypatch)
        gen = generator(config(), RecordingClient(), passes=1, request_delay=5.0)
        # `_ask_all` is the unit under test. `run()` splits the battery into an initial
        # and a revision phase, and each phase opens its own request sequence — testing
        # through it would be asserting the phase split, not the pacing.
        asyncio.run(gen._ask_all(PROBES))
        # One wait fewer than there are requests: the first goes out immediately and the
        # run is never padded by a trailing sleep.
        assert slept == [5.0] * (len(PROBES) - 1)

    def test_pacing_spans_passes_as_well_as_probes(self, monkeypatch):
        slept = self._timed(monkeypatch)
        gen = generator(config(), RecordingClient(), passes=3, request_delay=2.0)
        asyncio.run(gen._ask_all(PROBES))
        assert slept == [2.0] * (len(PROBES) * 3 - 1)

    def test_zero_delay_is_exactly_the_old_behaviour(self, monkeypatch):
        slept = self._timed(monkeypatch)
        gen = generator(config(), RecordingClient(), passes=2, request_delay=0.0)
        asyncio.run(gen._ask_all(PROBES))
        assert slept == []

    def test_the_config_supplies_the_default_and_the_argument_overrides_it(self):
        cfg = config()
        cfg.battery.request_delay_seconds = 7.5
        assert generator(cfg, RecordingClient()).request_delay == 7.5
        # An explicit 0 is an instruction, not silence — it must not fall back.
        assert generator(cfg, RecordingClient(), request_delay=0.0).request_delay == 0.0
        assert generator(cfg, RecordingClient(), request_delay=1.5).request_delay == 1.5

    def test_a_negative_delay_is_refused(self):
        with pytest.raises(GenerationError, match="must not be negative"):
            generator(config(), RecordingClient(), request_delay=-1.0)
