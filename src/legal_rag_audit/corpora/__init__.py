"""The corpus library (§9.5) — domain corpora as versioned, reusable assets.

Two halves, and the split between them is the whole idea:

* `spine.py` — the roles a corpus must fill. Domain-invariant, in code, checked at import.
* `library/` — one directory per corpus, holding the prose that fills them.

§9.5's claim is that the fifth corpus in a practice area takes half a day because it is a
template edit. That is only true if there is nothing left to design by the time an author
starts, and nothing to discover later: the spine decides the structure, and the loader
refuses a corpus that does not satisfy it, naming what is absent. Both halves are load
bearing — a spine without a validating loader is documentation, and a loader without a
spine has nothing to validate against.
"""

from .library import (
    DEFAULT,
    SKELETON,
    CorpusSpecError,
    DocumentEntry,
    DomainCorpus,
    StalenessTrigger,
    available,
    library_root,
    load,
    resolve,
)
from .spine import (
    BASE,
    BY_KEY,
    DOCUMENT_KEYS,
    MANDATORY,
    REVISION,
    ROLES,
    SPINE,
    DocumentSpec,
    Role,
    SpineError,
)

__all__ = [
    "BASE",
    "BY_KEY",
    "CorpusSpecError",
    "DEFAULT",
    "DOCUMENT_KEYS",
    "DocumentEntry",
    "DocumentSpec",
    "DomainCorpus",
    "MANDATORY",
    "REVISION",
    "ROLES",
    "Role",
    "SKELETON",
    "SPINE",
    "SpineError",
    "StalenessTrigger",
    "available",
    "library_root",
    "load",
    "resolve",
]
