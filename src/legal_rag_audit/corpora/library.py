"""The corpus library — reading a domain corpus off disk and checking it against the spine.

A corpus is a directory:

    <name>/
        corpus.yaml           metadata, staleness triggers, document inventory, probes
        documents/            one file per document, bodies carrying @@plant-id@@ slots
        documents/revision/   the second state of any document that gets replaced
        README.md             what this corpus is for and what it cannot establish

`load()` reads one, validates it against `spine.SPINE`, and returns a `DomainCorpus`
carrying `templates` in exactly the shape `plants.pipeline` already consumes. So the
planting pipeline, the collision guard, the ground-truth manifest and the reference
target are all unchanged by the existence of a second corpus — which is the point.

**Validation is the deliverable, not a safety net.** §9.5 promises the fifth corpus in a
practice area takes half a day. That is only true if the author is *told* what is missing
rather than discovering it when a check fails against a live target. So the loader refuses,
with the reason, a corpus that:

* omits a document key, or invents one;
* omits a slot the spine declares, or carries one it does not;
* declares a slot in `corpus.yaml` that the body has no marker for, or the reverse;
* leaves a probe unworded, or words a probe the battery does not ask;
* has a document below §9.5 item 1's three-invariant floor for a reason the spine does
  not record;
* still contains authoring placeholders.

Every one of those is a defect that would otherwise reach a report as a finding about
somebody else's system, which NF9 forbids.

**Where corpora live.** Inside the package, under `library/`. §5.2's repository layout puts
`corpora/` at the repository root, and that is where a reader looks — but a directory
outside the package cannot be shipped in the wheel, and the bundled demo has to run from a
`pip install`. `tests/test_corpus_packaging.py` exists because it once silently did not.
Two locations would mean two lookup rules and a corpus that resolves in a working tree and
not from an install, so there is one.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Optional

import yaml

from ..plants.templates import SLOT, Slot, Template
from .spine import (
    BASE,
    BY_KEY,
    DOCUMENT_KEYS,
    REVISION,
    ROLES,
    SPINE,
    DocumentSpec,
)

#: The corpus every try-it path uses when nothing else is named.
DEFAULT: Final = "bundled-demo"

#: The skeleton an author copies. Excluded from `available()` — it is deliberately
#: incomplete and deliberately fails to load.
SKELETON: Final = "TEMPLATE"

#: What an unwritten field looks like in the skeleton. A corpus still carrying one is
#: refused: a `TODO` reaching a target as a document body would produce findings about a
#: document nobody wrote.
PLACEHOLDER: Final = re.compile(r"\bTODO\b")

#: Placeholder in probe wording, resolved to a plant value when the battery is built. A
#: question may legitimately have to name a heading — you cannot ask about a support band
#: without naming it. What it may never name is the answer, which `probes.battery`
#: enforces against the expectations.
PLANT_REF: Final = re.compile(r"\{plant:([a-z0-9\-]+)\}")

DOCUMENTS: Final = "documents"
MANIFEST: Final = "corpus.yaml"


class CorpusSpecError(Exception):
    """A corpus does not satisfy the spine. A setup problem, not a finding (NF9)."""


@dataclass(frozen=True)
class StalenessTrigger:
    """What, if amended, invalidates this corpus (§9.5 item 2).

    The re-run trigger built into the artefact rather than chased by email. It is prose
    on purpose: the thing that goes stale is a legal position, and no schema we could
    write would decide for a reader whether an amendment reached it.
    """

    instrument: str
    invalidates: str
    #: Where to check. Optional — some triggers are watched by a person, not a URL.
    watch: Optional[str] = None


@dataclass(frozen=True)
class DocumentEntry:
    """One document as the corpus author supplied it."""

    key: str
    state: str
    filename: str
    #: How a reader — and an answer being scored for attribution — names this document.
    #: `attribution` scores a fact against its identifier, so this string is ground truth
    #: and not decoration.
    identifier: str
    #: plant_id -> where in the document it sits, in words. Goes into the ground-truth
    #: manifest so a client reading the disclosed key can find the plant in the document
    #: they were sent.
    locations: dict[str, str]
    body: str


@dataclass(frozen=True)
class DomainCorpus:
    """A loaded, validated corpus and everything downstream needs from it."""

    name: str
    version: int
    domain: str
    jurisdiction: str
    as_at: str
    description: str
    staleness_triggers: tuple[StalenessTrigger, ...]
    documents: tuple[DocumentEntry, ...]
    #: Facts the battery treats as known and deliberately **out of corpus** (§8.2 #6).
    #: Nothing is planted for parametric bleed — the point is absence. Real, famous
    #: authorities a base model reliably knows and no document here mentions, so their
    #: appearance in an answer is evidence of the model's weights rather than of
    #: retrieval. Per corpus rather than global, because the authority that a model
    #: reliably knows is a question about the practice area.
    out_of_corpus: tuple[str, ...]
    #: probe_id -> the wording of the question in this domain.
    probes: dict[str, str]
    templates: tuple[Template, ...]
    #: SHA-256 over the manifest and every document body. §9.5 item 4 — the hash goes in
    #: the run manifest and the version goes on the attestation, so a reader can tell a
    #: run of commercial-contracts v2 from one of v1.
    digest: str
    path: str = field(compare=False, default="")

    @property
    def label(self) -> str:
        return f"{self.name} v{self.version}"

    def entry(self, key: str, state: str = BASE) -> DocumentEntry:
        for document in self.documents:
            if document.key == key and document.state == state:
                return document
        raise CorpusSpecError(f"{self.name}: no document {key!r} in state {state!r}")

    def filename(self, key: str) -> str:
        return self.entry(key).filename

    def identifier(self, key: str) -> str:
        return self.entry(key).identifier


# --------------------------------------------------------------------------------
# Locating a corpus
# --------------------------------------------------------------------------------


def library_root() -> str:
    return os.path.join(os.path.dirname(__file__), "library")


def available() -> list[str]:
    """Corpus names that ship with this build, in name order. Excludes the skeleton."""
    root = Path(library_root())
    if not root.is_dir():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name != SKELETON and (p / MANIFEST).is_file()
    )


def resolve(name_or_path: Optional[str]) -> str:
    """A corpus name or a directory path, resolved to a directory.

    Names are looked up in the shipped library; anything containing a separator, or
    naming an existing directory, is taken as a path. That lets an engagement keep its
    own corpora outside this repository without a second configuration key.
    """
    candidate = name_or_path or DEFAULT

    inside = os.path.join(library_root(), candidate)
    if os.path.isdir(inside):
        return inside

    if os.path.isdir(candidate):
        return candidate

    known = ", ".join(available()) or "(none — this build shipped no corpora)"
    raise CorpusSpecError(
        f"no corpus named {candidate!r}.\n"
        f"  This build ships: {known}\n"
        f"  A corpus may also be given as a path to a directory holding {MANIFEST}.\n"
        f"  See corpora/README.md for how to author one."
    )


# --------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------


def _require(mapping: dict, key: str, where: str) -> Any:
    if key not in mapping:
        raise CorpusSpecError(f"{where}: `{key}` is missing")
    return mapping[key]


def load(name_or_path: Optional[str] = None) -> DomainCorpus:
    """Read a corpus and refuse it unless it satisfies the spine."""
    path = resolve(name_or_path)
    manifest_path = os.path.join(path, MANIFEST)
    if not os.path.isfile(manifest_path):
        raise CorpusSpecError(
            f"{path} is not a corpus: no {MANIFEST}.\n"
            f"  Copy corpora/{SKELETON}/ and fill it in; it fails to load until you do, "
            f"naming what is left."
        )

    raw_manifest = Path(manifest_path).read_text(encoding="utf-8")
    try:
        manifest = yaml.safe_load(raw_manifest) or {}
    except yaml.YAMLError as e:
        raise CorpusSpecError(f"{manifest_path}: not readable as YAML\n  {e}") from e
    if not isinstance(manifest, dict):
        raise CorpusSpecError(f"{manifest_path}: expected a mapping at the top level")

    name = str(_require(manifest, "corpus", manifest_path))
    version = _require(manifest, "version", manifest_path)
    if not isinstance(version, int) or version < 1:
        raise CorpusSpecError(
            f"{manifest_path}: `version` must be a positive integer, got {version!r}.\n"
            f"  It goes on the attestation (§9.5 item 4). A reader comparing two reports "
            f"has to be able to tell whether they used the same corpus."
        )

    declared = _require(manifest, "documents", manifest_path)
    if not isinstance(declared, dict):
        raise CorpusSpecError(f"{manifest_path}: `documents` must be a mapping")

    documents = _read_documents(path, name, declared)
    _check_documents(name, documents)

    probes = _read_probes(manifest, manifest_path, name)
    triggers = _read_triggers(manifest, manifest_path)
    out_of_corpus = _read_out_of_corpus(manifest, manifest_path, name, documents)

    return DomainCorpus(
        name=name,
        version=version,
        domain=str(_require(manifest, "domain", manifest_path)),
        jurisdiction=str(_require(manifest, "jurisdiction", manifest_path)),
        as_at=str(_require(manifest, "as_at", manifest_path)),
        description=str(manifest.get("description", "")).strip(),
        staleness_triggers=triggers,
        documents=documents,
        out_of_corpus=out_of_corpus,
        probes=probes,
        templates=_templates(documents),
        digest=_digest(raw_manifest, documents),
        path=path,
    )


def _read_documents(
    path: str, name: str, declared: dict
) -> tuple[DocumentEntry, ...]:
    """One entry per spine document, read in spine order."""
    unknown = sorted(set(declared) - set(DOCUMENT_KEYS))
    if unknown:
        raise CorpusSpecError(
            f"{name}: {MANIFEST} declares document keys the spine does not have: "
            f"{unknown}.\n"
            f"  A corpus supplies prose for the roles in `corpora/spine.py`; it does not "
            f"add roles. An extra document is either a typo or a check nobody wired up, "
            f"and both would ship a document nothing scores."
        )

    entries: list[DocumentEntry] = []
    for spec in SPINE:
        if spec.key not in declared:
            raise CorpusSpecError(
                f"{name}: no document for {spec.key!r}.\n"
                f"  What it is for: {spec.purpose}\n"
                f"  Invariants it must carry: {', '.join(spec.plant_ids())}"
            )
        entry = declared[spec.key]
        if not isinstance(entry, dict):
            raise CorpusSpecError(f"{name}: document {spec.key!r} must be a mapping")

        filename = _require(entry, "filename", f"{name}: document {spec.key!r}")
        identifier = _require(entry, "identifier", f"{name}: document {spec.key!r}")

        block = entry
        if spec.state == REVISION:
            block = entry.get("revision")
            if not isinstance(block, dict):
                raise CorpusSpecError(
                    f"{name}: document {spec.key!r} needs a `revision:` block.\n"
                    f"  What it is for: {spec.purpose}\n"
                    f"  The revised body goes in {DOCUMENTS}/{REVISION}/{filename} and "
                    f"replaces the base document by name mid-run (§8.2 #4)."
                )

        locations = block.get("slots") or {}
        if not isinstance(locations, dict):
            raise CorpusSpecError(
                f"{name}: document {spec.key!r} `slots` must map plant id -> location"
            )

        body_path = (
            os.path.join(path, DOCUMENTS, REVISION, str(filename))
            if spec.state == REVISION
            else os.path.join(path, DOCUMENTS, str(filename))
        )
        entries.append(
            DocumentEntry(
                key=spec.key,
                state=spec.state,
                filename=str(filename),
                identifier=str(identifier),
                locations={str(k): str(v) for k, v in locations.items()},
                body=_read_body(body_path, name, spec),
            )
        )
    return tuple(entries)


def _read_body(body_path: str, name: str, spec: DocumentSpec) -> str:
    try:
        body = Path(body_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CorpusSpecError(
            f"{name}: document {spec.key!r} names a file that is not there.\n"
            f"  expected at: {body_path}\n"
            f"  What it is for: {spec.purpose}"
        ) from None
    except UnicodeDecodeError as e:
        raise CorpusSpecError(
            f"{name}: {body_path} is not UTF-8 text.\n  {e}\n"
            f"  The corpus is used verbatim as ground truth, so it must be text."
        ) from e
    if not body.strip():
        raise CorpusSpecError(f"{name}: {body_path} is empty")
    return body


def _check_documents(name: str, documents: tuple[DocumentEntry, ...]) -> None:
    """Every spine slot present in the body and located in the manifest, and no others."""
    for document in documents:
        spec = BY_KEY[(document.key, document.state)]
        where = f"{name}: {document.filename}"
        if document.state == REVISION:
            where += f" ({REVISION})"

        if PLACEHOLDER.search(document.body):
            raise CorpusSpecError(
                f"{where}: still contains an authoring placeholder.\n"
                f"  A corpus copied from {SKELETON}/ does not load until every TODO is "
                f"replaced. A placeholder reaching a target as a document body would "
                f"produce findings about a document nobody wrote."
            )

        required = set(spec.plant_ids())
        in_body = set(SLOT.findall(document.body))

        if absent := sorted(required - in_body):
            raise CorpusSpecError(
                f"{where}: the body has no slot for {absent}.\n"
                f"  Write `@@{absent[0]}@@` where the invariant belongs. A plant that is "
                f"minted and never inserted is in the answer key and not in the corpus, "
                f"so the check against it fails a correct system."
            )
        if extra := sorted(in_body - required):
            raise CorpusSpecError(
                f"{where}: the body has slots the spine does not declare: {extra}.\n"
                f"  Nothing mints them, so they would ship into the corpus as literal "
                f"`@@` markers."
            )

        if unlocated := sorted(required - set(document.locations)):
            raise CorpusSpecError(
                f"{where}: no location recorded for {unlocated}.\n"
                f"  §9.5 item 1 wants invariants registered at authoring time. The "
                f"location is what lets a client holding the disclosed key find the plant "
                f"in the document they were sent, so 'somewhere in the file' is not it."
            )
        if stray := sorted(set(document.locations) - required):
            raise CorpusSpecError(
                f"{where}: locations recorded for plants this document does not carry: "
                f"{stray}"
            )
        for plant_id, location in document.locations.items():
            if not location.strip():
                raise CorpusSpecError(f"{where}: location for {plant_id!r} is blank")


def _read_probes(manifest: dict, manifest_path: str, name: str) -> dict[str, str]:
    """The domain's wording for every probe the battery asks.

    Imported lazily: `probes.battery` imports the planting pipeline, which imports this
    module. The battery is the authority on which probes exist, so the alternative — a
    second list here — is the kind of duplicate that goes out of step silently.
    """
    from ..probes.battery import BATTERY

    declared = manifest.get("probes") or {}
    if not isinstance(declared, dict):
        raise CorpusSpecError(f"{manifest_path}: `probes` must map probe id -> question")

    expected = {entry.probe_id for entry in BATTERY}
    if missing := sorted(expected - set(declared)):
        raise CorpusSpecError(
            f"{name}: {len(missing)} probe(s) unworded: {missing}\n"
            f"  A question has to be asked in the domain's own language or it retrieves "
            f"nothing, and a check whose probe retrieves nothing reports a finding about "
            f"our wording rather than their system."
        )
    if unknown := sorted(set(declared) - expected):
        raise CorpusSpecError(
            f"{name}: {MANIFEST} words probes the battery does not ask: {unknown}"
        )

    answers = {
        entry.probe_id: _answers_to(entry)
        for entry in BATTERY
    }

    probes = {}
    for probe_id, text in declared.items():
        probe_id = str(probe_id)
        text = str(text).strip()
        if not text:
            raise CorpusSpecError(f"{name}: probe {probe_id!r} has no question")
        if PLACEHOLDER.search(text):
            raise CorpusSpecError(
                f"{name}: probe {probe_id!r} still contains an authoring placeholder"
            )

        referenced = set(PLANT_REF.findall(text))
        if unknown := sorted(referenced - {r.plant_id for r in ROLES}):
            raise CorpusSpecError(
                f"{name}: probe {probe_id!r} references plants the spine does not "
                f"declare: {unknown}"
            )
        # A question that names its own answer measures nothing. Enforced rather than
        # left to the author: `{plant:...}` exists so a question can name a *heading* it
        # would otherwise be unable to retrieve on, and the difference between a heading
        # and an answer is exactly whether the check scores it.
        if leaked := sorted(referenced & answers[probe_id]):
            raise CorpusSpecError(
                f"{name}: probe {probe_id!r} quotes the answer it is scored on: "
                f"{leaked}.\n"
                f"  `{{plant:...}}` is for identifiers a question cannot retrieve without "
                f"— a band name, a document title. An expected invariant put into the "
                f"question makes the answer an echo, and the check would pass a system "
                f"that retrieved nothing."
            )
        probes[probe_id] = text
    return probes


def _answers_to(entry: Any) -> set[str]:
    """The plant ids a probe is scored for containing — its answers, in short."""
    from ..probes.battery import P

    found: set[str] = set()
    for fields in entry.expectations.values():
        for item in fields.get("must_contain", []):
            if isinstance(item, P):
                found.add(item.plant_id)
        for pairing in fields.get("adjacency", []):
            # The `fact` only. An adjacency pairing's `identifier` is precisely the handle
            # a question is allowed to name — you cannot ask about a support band without
            # naming the band, and the check is whether the *figure* comes back attached
            # to it.
            if isinstance(pairing.get("fact"), P):
                found.add(pairing["fact"].plant_id)
        side_effect = fields.get("side_effect") or {}
        if isinstance(side_effect.get("value"), P):
            found.add(side_effect["value"].plant_id)
    return found


def _read_out_of_corpus(
    manifest: dict,
    manifest_path: str,
    name: str,
    documents: tuple[DocumentEntry, ...],
) -> tuple[str, ...]:
    """The parametric-bleed lure, and the check that it is genuinely absent.

    The whole finding is *this came from the weights, not from retrieval*. If the phrase
    turns out to be in a document, a correct system quoting its own corpus is recorded as
    having bled — a false positive, which §14.2 makes a release blocker. So it is checked
    here rather than trusted, and the check is over every body including the revision.
    """
    declared = manifest.get("out_of_corpus")
    if not declared:
        raise CorpusSpecError(
            f"{manifest_path}: `out_of_corpus` is missing or empty.\n"
            f"  §8.2 #6 scores parametric bleed by absence: a real authority the model "
            f"reliably knows and no document here mentions. Nothing is planted for it, so "
            f"a corpus that names none cannot exercise the check at all."
        )
    if not isinstance(declared, list):
        raise CorpusSpecError(f"{manifest_path}: `out_of_corpus` must be a list")

    phrases = tuple(str(item).strip() for item in declared)
    for phrase in phrases:
        if not phrase:
            raise CorpusSpecError(f"{manifest_path}: `out_of_corpus` has a blank entry")
        for document in documents:
            if phrase.lower() in document.body.lower():
                raise CorpusSpecError(
                    f"{name}: {phrase!r} is listed as out of corpus and appears in "
                    f"{document.filename}.\n"
                    f"  Parametric bleed is scored by absence. A system quoting its own "
                    f"corpus would be recorded as having answered from its weights, "
                    f"which is a false positive against a correct system."
                )
    return phrases


def _read_triggers(manifest: dict, manifest_path: str) -> tuple[StalenessTrigger, ...]:
    """§9.5 item 2 — which instruments, if amended, invalidate this corpus.

    An empty list is allowed and means something: a corpus built entirely from synthetic
    documents has no legal position to go stale. It is not the same as a corpus whose
    author did not think about it, which is why the key is required and the list is not.
    """
    if "staleness_triggers" not in manifest:
        raise CorpusSpecError(
            f"{manifest_path}: `staleness_triggers` is missing.\n"
            f"  §9.5 item 2 requires it. An empty list is a legitimate answer for a "
            f"corpus with no legal position in it — the key is required so that the "
            f"answer is a decision rather than an omission."
        )
    declared = manifest["staleness_triggers"] or []
    if not isinstance(declared, list):
        raise CorpusSpecError(f"{manifest_path}: `staleness_triggers` must be a list")

    triggers = []
    for index, item in enumerate(declared):
        where = f"{manifest_path}: staleness_triggers[{index}]"
        if not isinstance(item, dict):
            raise CorpusSpecError(f"{where}: expected a mapping")
        triggers.append(
            StalenessTrigger(
                instrument=str(_require(item, "instrument", where)),
                invalidates=str(_require(item, "invalidates", where)),
                watch=str(item["watch"]) if item.get("watch") else None,
            )
        )
    return tuple(triggers)


def _templates(documents: tuple[DocumentEntry, ...]) -> tuple[Template, ...]:
    """The corpus in the shape `plants.pipeline` already consumes.

    In spine order, because declaration order is what makes planting reproducible: a
    dict ordering that varied would give two people with the same seed two different
    batteries.
    """
    return tuple(
        Template(
            name=document.filename,
            body=document.body,
            state=document.state,
            tenant=BY_KEY[(document.key, document.state)].tenant,
            namespace=BY_KEY[(document.key, document.state)].namespace,
            slots=tuple(
                Slot(
                    plant_id=role.plant_id,
                    kind=role.kind,
                    location=document.locations[role.plant_id],
                    companions=role.companions,
                )
                for role in BY_KEY[(document.key, document.state)].roles
            ),
        )
        for document in documents
    )


def _digest(raw_manifest: str, documents: tuple[DocumentEntry, ...]) -> str:
    """One hash over the manifest and every body, in a fixed order.

    Not the same digest `hash --corpus` produces — that seals the *planted* tree, values
    and all, and is what a pre-commitment rests on (§3.6). This one identifies the corpus
    the plants were inserted into, which is what a reader needs to compare two runs.
    """
    digest = hashlib.sha256()
    digest.update(b"corpus.v1\n")
    digest.update(raw_manifest.encode("utf-8"))
    for document in sorted(documents, key=lambda d: (d.state, d.filename)):
        digest.update(f"\n{document.state}/{document.filename}\n".encode("utf-8"))
        digest.update(document.body.encode("utf-8"))
    return digest.hexdigest()
