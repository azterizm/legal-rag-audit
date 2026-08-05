"""The local snapshot store — corroboration for the anchors, not an input to scoring.

The division of labour is the point of this module, so it is worth stating plainly:

* **`anchors.py` is committed and is the ground truth.** It carries the phrase, the date
  and the source URL. The battery is built and scored from it alone, offline, with no
  network and no ingestion step.
* **The store is built by `ingest` and is not committed.** It records that each anchor's
  phrase really did appear in the provision at that date, on the day we looked, together
  with the digest of the bytes that said so.

The alternative — scoring directly against fetched text — was rejected. It would make
every run depend on a third party being up and returning the same bytes, put a network
fetch inside the one command that must work offline, and mean a report's ground truth
could change between two runs of the same battery without anyone deciding that it should.

**Excerpts, not provisions.** A snapshot keeps a bounded window around the phrase rather
than the whole section. `legislation.gov.uk` publishes under the Open Government Licence
so storing the full text would be permitted; the reasons not to are that the footprint
compounds per date per section, and that a store holding whole provisions invites being
used as the ground truth, which is the thing this split exists to prevent.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .anchors import ANCHORS, Anchor, Reading

#: Characters kept either side of the phrase. Enough to read the sentence it sits in and
#: satisfy yourself it means what the anchor says; not enough to be a copy of the section.
EXCERPT_WINDOW = 160

STORE_VERSION = "statute_store.v1"


class StoreError(Exception):
    """The store could not be read or does not describe the anchors. Never a finding."""


@dataclass(frozen=True)
class Snapshot:
    """One anchor reading, checked against the source on one day."""

    anchor_id: str
    as_at: Optional[str]
    source_url: str
    #: When we looked. A snapshot is a statement about that moment and nothing else.
    retrieved: str
    #: SHA-256 of the exact bytes returned. Two people running `ingest` on the same day
    #: can compare this without comparing prose.
    digest: str
    bytes_fetched: int
    invariant: str
    invariant_present: bool
    excerpt: str
    licence: str

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Store:
    snapshots: list[Snapshot] = field(default_factory=list)
    version: str = STORE_VERSION

    # -- persistence -------------------------------------------------------------

    def to_document(self) -> dict[str, Any]:
        return {
            "schema": self.version,
            "written": _now(),
            "snapshots": [s.to_record() for s in self.snapshots],
        }

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_document(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Store":
        p = Path(path)
        if not p.exists():
            raise StoreError(
                f"{p}: no statute store.\n"
                f"  The battery does not need one — anchors are committed and scoring is\n"
                f"  offline. Build it to re-check them against the source:\n"
                f"    legal-rag-audit ingest -o {p}"
            )
        try:
            document = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise StoreError(f"{p}: not valid JSON ({e.msg} at line {e.lineno}).") from None
        if document.get("schema") != STORE_VERSION:
            raise StoreError(
                f"{p}: schema is {document.get('schema')!r}, expected "
                f"{STORE_VERSION!r}. Re-run `ingest`."
            )
        return cls(
            snapshots=[Snapshot(**s) for s in document.get("snapshots", [])],
            version=STORE_VERSION,
        )

    # -- what it is for ----------------------------------------------------------

    def find(self, anchor_id: str, as_at: Optional[str]) -> Optional[Snapshot]:
        return next(
            (
                s
                for s in self.snapshots
                if s.anchor_id == anchor_id and s.as_at == as_at
            ),
            None,
        )

    def drift(self, anchors: tuple[Anchor, ...] = ANCHORS) -> list[str]:
        """Anchors the store does not corroborate, in words a person can act on.

        Two kinds, and they mean opposite things. A missing snapshot means nobody has
        looked yet. A snapshot whose phrase was *absent* means the law moved, or our
        reading of it was wrong — and the second is the one worth waking up for, because
        the battery would go on scoring answers against a version that no longer exists.
        """
        problems: list[str] = []
        for anchor in anchors:
            for reading in anchor.readings:
                snapshot = self.find(anchor.anchor_id, reading.as_at)
                where = f"{anchor.anchor_id} @ {reading.as_at or 'current'}"
                if snapshot is None:
                    problems.append(f"{where}: never fetched")
                elif not snapshot.invariant_present:
                    problems.append(
                        f"{where}: {reading.invariant!r} was not in the provision at "
                        f"{snapshot.source_url} when it was fetched on "
                        f"{snapshot.retrieved[:10]}"
                    )
                elif snapshot.invariant != reading.invariant:
                    problems.append(
                        f"{where}: the anchor now says {reading.invariant!r} but the "
                        f"snapshot was taken against {snapshot.invariant!r}"
                    )
        return problems

    def footprint(self) -> dict[str, Any]:
        """What this costs to keep, so §20.1 item 3 is answered with a number.

        The open decision was whether versioned statute data is affordable to hold
        locally. For a bounded anchor set the answer is that it is not close: the store
        is smaller than a photograph, because it keeps phrases rather than statutes.
        """
        stored = sum(len(s.excerpt.encode("utf-8")) for s in self.snapshots)
        fetched = sum(s.bytes_fetched for s in self.snapshots)
        return {
            "snapshots": len(self.snapshots),
            "stored_bytes": stored,
            "fetched_bytes": fetched,
            "retained_fraction": round(stored / fetched, 5) if fetched else None,
        }


def excerpt_around(text: str, phrase: str, window: int = EXCERPT_WINDOW) -> str:
    """A bounded window around the phrase, or the head of the text if it is absent."""
    normalised = " ".join((text or "").split())
    index = normalised.casefold().find(" ".join(phrase.split()).casefold())
    if index < 0:
        return normalised[: window * 2]
    start = max(0, index - window)
    end = min(len(normalised), index + len(phrase) + window)
    return ("…" if start else "") + normalised[start:end] + ("…" if end < len(normalised) else "")


def snapshot_for(
    anchor: Anchor,
    reading: Reading,
    body: bytes,
    text: str,
) -> Snapshot:
    """Build a snapshot from bytes already fetched. Pure, so it is testable offline."""
    import hashlib

    normalised = " ".join((text or "").split()).casefold()
    present = " ".join(reading.invariant.split()).casefold() in normalised
    return Snapshot(
        anchor_id=anchor.anchor_id,
        as_at=reading.as_at,
        source_url=anchor.url(reading),
        retrieved=_now(),
        digest="sha256:" + hashlib.sha256(body).hexdigest(),
        bytes_fetched=len(body),
        invariant=reading.invariant,
        invariant_present=present,
        excerpt=excerpt_around(text, reading.invariant),
        licence=anchor.licence,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
