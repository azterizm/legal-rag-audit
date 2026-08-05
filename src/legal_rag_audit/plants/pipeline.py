"""The planting pipeline — a corpus in, a planted corpus and an answer key out.

One function does the work. `plant(seed, corpus)` walks the corpus's documents in spine
order, mints each slot through the collision guard, substitutes the values, and returns
both halves of the run: the documents to upload, and the plants as the ground-truth
manifest records them. Spine order is what makes it reproducible — a set iteration or a
dict ordering that varied would give two people with the same seed two different
batteries, which is the one thing this module cannot do.

**Which corpus.** Named, never assumed. Phase H made the documents a data artefact
(§9.5), so a run planting the employment corpus and a run planting the commercial-contracts
one differ in their documents and in nothing else — same seed derivation, same guard, same
manifest shape. The corpus name, version and digest travel with the result, because two
reports that used different corpora and say so are comparable and two that do not are not.

Layout on disk, because it is a contract with the `hash` and `generate` commands:

    <out>/corpus/base/       every document in its first state — uploaded first
    <out>/corpus/revision/   documents that replace their base counterpart later
    <out>/probes.jsonl       the questions
    <out>/ground_truth.json  the sealed answer key

`hash --corpus <out>/corpus` therefore seals both states in one tree digest. Splitting
them into two hashed artefacts would let the revised fee be chosen after the first
phase's answers came back, which is the whole thing §3.6 exists to prevent.

**The published demo seed.** With no seed supplied the pipeline uses a fixed, published
one and says so in the manifest. That makes the try-it path reproducible for everyone,
and it makes the demo run structurally distinguishable from an engagement: a report whose
seed is the published one cannot claim its plants were unguessable, and it does not.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Optional

from ..interchange.ground_truth import Plant
from .guard import Guard
from .mint import RECIPE
from .templates import SLOT, Template, unplanted

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime only
    from ..corpora.library import DomainCorpus

#: The seed for the try-it battery. Published on purpose: anyone can regenerate the demo
#: corpus and check it against the one they were sent. An engagement supplies its own,
#: and the difference is recorded rather than assumed.
PUBLISHED_DEMO_SEED: Final = "legal-rag-audit/demo/v2"

PUBLISHED = "the published demo seed — this battery is reproducible by anyone"
SUPPLIED = "supplied for this run"


class PlantingError(Exception):
    """The corpus could not be planted. A setup problem, not a finding (NF9)."""


@dataclass(frozen=True)
class PlantedCorpus:
    seed: str
    seed_source: str
    #: filename -> body, in the state uploaded first.
    documents: dict[str, str]
    #: filename -> body, replacing the base document after the first phase.
    revisions: dict[str, str]
    plants: tuple[Plant, ...]
    #: plant_id -> value. The battery builds expectations from this; nothing else should
    #: need it, and nothing that writes a probe file may see it.
    values: dict[str, str]
    guard: dict
    #: The corpus these documents came from. Carried rather than looked up again, because
    #: a report has to name the corpus that produced it (§9.5 item 4) and a second read of
    #: the directory could return something else.
    source: "DomainCorpus"

    def value(self, plant_id: str) -> str:
        try:
            return self.values[plant_id]
        except KeyError:
            raise PlantingError(
                f"no plant named {plant_id!r}. The battery expects a plant the templates\n"
                f"  do not declare — one of the two was edited without the other, and an\n"
                f"  expectation scored against a plant that does not exist would be a\n"
                f"  finding manufactured from our own missing data (NF9)."
            ) from None

    def is_demo(self) -> bool:
        return self.seed == PUBLISHED_DEMO_SEED


def plant(
    seed: Optional[str] = None, corpus: Optional["DomainCorpus"] = None
) -> PlantedCorpus:
    """Mint every declared plant and substitute it into its document."""
    from ..corpora.library import load

    resolved = seed or PUBLISHED_DEMO_SEED
    if not resolved.strip():
        raise PlantingError(
            "the run seed is empty. A seed is the only thing that makes a battery\n"
            "  reproducible and unguessable at the same time; an empty one is neither."
        )

    source = corpus if corpus is not None else load()
    templates = source.templates

    guard = Guard.over({t.name + "#" + t.state: unplanted(t.body) for t in templates})

    values: dict[str, str] = {}
    plants: list[Plant] = []

    for template in templates:
        for slot in template.slots:
            if slot.plant_id in values:
                raise PlantingError(
                    f"plant id {slot.plant_id!r} is declared twice in the templates.\n"
                    f"  Plant ids key the ground truth; a duplicate makes it ambiguous\n"
                    f"  which document a finding points at."
                )
            minted, attempt = guard.mint(slot.kind, resolved, slot.plant_id)
            values[slot.plant_id] = minted.value
            plants.append(
                Plant(
                    plant_id=slot.plant_id,
                    type=slot.kind,
                    value=minted.value,
                    document=template.name,
                    state=template.state,
                    tenant=template.tenant,
                    namespace=template.namespace,
                    location=slot.location,
                    companions=list(slot.companions),
                    attempt=attempt,
                )
            )

    documents = {t.name: _substitute(t, values) for t in templates if t.state == "base"}
    revisions = {
        t.name: _substitute(t, values) for t in templates if t.state == "revision"
    }

    return PlantedCorpus(
        seed=resolved,
        seed_source=PUBLISHED if resolved == PUBLISHED_DEMO_SEED else SUPPLIED,
        documents=documents,
        revisions=revisions,
        plants=tuple(plants),
        values=values,
        guard={**guard.record(), "recipe": RECIPE},
        source=source,
    )


def _substitute(template: Template, values: dict[str, str]) -> str:
    """Fill every slot, refusing a template that names a plant nobody minted."""

    def replace(match) -> str:
        plant_id = match.group(1)
        if plant_id not in values:
            raise PlantingError(
                f"{template.name}: slot @@{plant_id}@@ has no declared plant.\n"
                f"  The body and the `slots` tuple disagree. An unfilled slot would ship\n"
                f"  the literal marker into the corpus and every check against it would\n"
                f"  fail for a reason that has nothing to do with the target."
            )
        return values[plant_id]

    filled = SLOT.sub(replace, template.body)

    declared = set(template.plant_ids())
    used = set(SLOT.findall(template.body))
    if unused := declared - used:
        raise PlantingError(
            f"{template.name}: declares {sorted(unused)} but the body has no slot for "
            f"them.\n"
            f"  A plant that is minted and never inserted is in the answer key and not\n"
            f"  in the corpus, so the check against it fails a correct system."
        )
    return filled


def write_corpus(directory: str | Path, corpus: PlantedCorpus) -> dict[str, int]:
    """Write `corpus/base/` and `corpus/revision/`. Returns what was written."""
    root = Path(directory)
    base = root / "base"
    base.mkdir(parents=True, exist_ok=True)
    for name, body in sorted(corpus.documents.items()):
        (base / name).write_text(body, encoding="utf-8")

    written = {"base": len(corpus.documents), "revision": 0}
    if corpus.revisions:
        revision = root / "revision"
        revision.mkdir(parents=True, exist_ok=True)
        for name, body in sorted(corpus.revisions.items()):
            (revision / name).write_text(body, encoding="utf-8")
        written["revision"] = len(corpus.revisions)
    return written
