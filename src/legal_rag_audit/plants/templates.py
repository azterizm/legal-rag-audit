"""The document model — a body with holes where the invariants go.

The documents themselves are no longer here. Phase H moved them onto disk as the corpus
library (§9.5): `corpora/spine.py` declares the roles a corpus must fill, and
`corpora/library/<name>/` holds the prose that fills them. What is left in this file is
the shape a corpus is read into, plus the two constants that are the *target's* vocabulary
rather than any domain's.

> [!IMPORTANT]
> **There is no longer such a thing as "the templates".** A run names a corpus, and the
> planting pipeline takes it as an argument. That is the change Phase H exists to make:
> §9.5's economics depend on a domain corpus being a data artefact somebody authors in
> half a day, not a Python tuple somebody edits.

Each slot is written `@@plant_id@@` and is replaced by `pipeline.plant()`. The marker is
chosen so it cannot occur in prose and so an unplanted document is obviously unplanted — a
template that leaked into a corpus directory would be visible at a glance rather than
looking like a document with an odd name in it.

**The three-invariant rule and where it is enforced.** §9.5 item 1 asks for at least three
invariants of at least two types per document, so that a system paraphrasing a leaked
clause still emits the counterparty name or the amount — a single planted string is
defeated by rewording. Which documents carry how many is a property of the *spine*, not of
any one corpus, so the rule is checked there: a document below the floor must record why,
and `corpora.spine` refuses one that does not. Five documents are below it and each names
its reason; all five are cases where a second invariant would give the question a second
correct answer, which would fail a correct system.
"""

import re
from dataclasses import dataclass
from typing import Final, Optional

#: Marker for a plant slot. Two at-signs either side: not a format string, so braces in
#: prose stay braces, and not a single delimiter that could occur by accident.
SLOT = re.compile(r"@@([a-z0-9\-]+)@@")


@dataclass(frozen=True)
class Slot:
    """One invariant and where it sits, declared with the document rather than inferred."""

    plant_id: str
    kind: str
    #: Where in the document, in words. Goes into the ground-truth manifest so a client
    #: reading the disclosed key can find the plant in the document they were sent.
    location: str
    #: Plants that must appear alongside this one for the answer to be complete. Absence
    #: of a companion is an omission finding, not a fabrication.
    companions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Template:
    name: str
    body: str
    slots: tuple[Slot, ...]
    tenant: Optional[str] = None
    #: The namespace a scoping-capable target should confine this document to. Null for
    #: documents that belong to the general set.
    namespace: Optional[str] = None
    #: The document state this body belongs to. `base` is uploaded first; `revision`
    #: replaces the base document after the first phase of probes, which is the only way
    #: to tell "not yet indexed" apart from "never invalidated" (§8.2 #4).
    state: str = "base"

    def plant_ids(self) -> tuple[str, ...]:
        return tuple(s.plant_id for s in self.slots)


def unplanted(body: str) -> str:
    """The body with its slots removed — what the collision guard checks against.

    Checking after planting would reject every plant, since by then each one is in the
    corpus by construction.
    """
    return SLOT.sub("", body)


#: Mask placeholders a re-hydration failure emits raw (§8.2 #5, third failure). Fixed
#: rather than planted, and not part of any corpus, because they are the target's own
#: vocabulary rather than ours — we are checking whether their masking layer leaks its
#: internal form into an answer, and that form does not change with the practice area.
MASK_TOKENS: Final[tuple[str, ...]] = (
    "[PERSON_1]",
    "[PERSON_2]",
    "[ORG_1]",
    "[ORG_2]",
    "[AMOUNT_1]",
    "[REDACTED]",
)
