"""Fetching versioned provisions from legislation.gov.uk (§9.2, §17.2 Phase G).

The refresh procedure, and the only part of this package that touches a network. It
exists to answer one question per anchor reading: **is the phrase we score against still
in the provision at that date?**

Nothing here feeds scoring. `ingest` writes a store, `store.drift()` reads it, and a
battery built with no store at all scores identically — see `store.py` for why that split
is deliberate rather than incidental.

**A wrong parse cannot produce ground truth.** The one thing this module cannot verify
for itself is that its extraction of CLML is right: a selector that silently matched
nothing would return an empty string, and an empty string contains no phrase. So the
anchor's phrase is the test of the fetch, not the other way round — a reading whose phrase
is absent from what came back is recorded as absent and named on the console, and
`--strict` turns it into a non-zero exit. That inverts the usual risk: a broken extractor
fails loudly on every anchor at once instead of quietly agreeing with whatever it found.

**Point-in-time URLs.** `legislation.gov.uk` addresses a provision as it stood on a date
by appending the date to the section path, and serves several representations of it. We
ask for `data.xml` — Crown copyright, published under the Open Government Licence v3.0 —
and take its text content, because the XML is the representation whose text nodes are the
provision rather than the site's furniture.
"""

import logging
from typing import Iterable, Optional

# The stdlib parser, deliberately, and the alternative is a dependency. `defusedxml`
# would harden this against entity-expansion attacks in a document we did not fetch
# ourselves. What we fetch is one `data.xml` per anchor reading from `legislation.gov.uk`
# over TLS, run by an operator refreshing a store — never during `generate` and never
# during `score`, so no target and no corpus reaches this parser. Adding a sixth library
# to the layer a target installs, to guard a path a target never executes, would cost
# more than it buys (docs/design.md, the dependency split). Hence the suppressions —
# Bandit's inline, Semgrep's on its own line because the two comment forms cannot share
# one.
#
# What the residual risk actually is, since both scanners say "XXE" and that is not it:
# `ElementTree` does not resolve external entities or retrieve a DTD, so the exposure a
# reader should weigh is an XML bomb — a denial of service, against an operator running
# a refresh, from a UK government publisher.
# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree  # nosec B405

from .anchors import ANCHORS, Anchor, Reading
from .store import Snapshot, Store, snapshot_for

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30.0

#: Sent so the operators of a free public service can see who is asking and why. They
#: publish this data for reuse; identifying ourselves is the least we owe them for it.
USER_AGENT = (
    "legal-rag-audit/0.2 (+https://github.com/; point-in-time anchor verification; "
    "a few requests per refresh)"
)


class IngestError(Exception):
    """The fetch could not be performed. A setup problem, never a finding (NF9)."""


def text_of(body: bytes) -> str:
    """Every text node of a CLML document, flattened.

    Deliberately structure-blind. The alternative is an XPath into `Legislation/…/P1para`
    that has to be right about namespaces, versions and the several shapes a provision
    can take — and be wrong silently when it is not. Flattening cannot be subtly wrong:
    it either contains the phrase or it does not, and the caller checks.
    """
    try:
        # Trusted source, operator-run path — see the note on the import.
        root = ElementTree.fromstring(body)  # nosec B314
    except ElementTree.ParseError as e:
        raise IngestError(f"the response was not parseable XML: {e}") from None
    return " ".join(part.strip() for part in root.itertext() if part and part.strip())


def readings(anchors: Iterable[Anchor]) -> list[tuple[Anchor, Reading]]:
    return [(anchor, reading) for anchor in anchors for reading in anchor.readings]


def fetch(anchor: Anchor, reading: Reading, client=None) -> Snapshot:
    """One provision at one date. Returns a snapshot whether or not the phrase was there."""
    import httpx

    url = anchor.url(reading) + "/data.xml"
    owned = client is None
    client = client or httpx.Client(
        timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )
    try:
        response = client.get(url)
        response.raise_for_status()
        body = response.content
    except Exception as e:  # noqa: BLE001 - the diagnosis matters, the class does not
        raise IngestError(
            f"{anchor.anchor_id} @ {reading.as_at or 'current'}: could not fetch {url}\n"
            f"  {type(e).__name__}: {e}\n"
            f"  The battery does not need this to run — anchors are committed and\n"
            f"  scoring is offline. What is unavailable is the check that they are\n"
            f"  still right."
        ) from None
    finally:
        if owned:
            client.close()

    return snapshot_for(anchor, reading, body, text_of(body))


def ingest(
    anchors: tuple[Anchor, ...] = ANCHORS,
    client=None,
    on_snapshot: Optional[object] = None,
) -> Store:
    """Fetch every anchor reading. Returns a store; raises only on transport failure."""
    store = Store()
    for anchor, reading in readings(anchors):
        snapshot = fetch(anchor, reading, client=client)
        store.snapshots.append(snapshot)
        if not snapshot.invariant_present:
            logger.warning(
                f"{anchor.anchor_id} @ {reading.as_at or 'current'}: "
                f"{reading.invariant!r} is not in {snapshot.source_url}"
            )
        if callable(on_snapshot):
            on_snapshot(anchor, reading, snapshot)
    return store
