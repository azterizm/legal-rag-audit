"""Seeded plant generation and the corpus planting pipeline (§3.2, Phase D).

The module that makes Tier 1 mean what it says. Every invariant the battery checks for
is minted here from a run seed, guarded against the three ways a token stops meaning one
thing, and inserted into a document at a location declared alongside it.

Imports nothing outside the interchange models, so it sits on the `generate` side of the
§5.3 dependency boundary — planting a corpus must not need the scoring layer.
"""

from .guard import CHECKED, MAX_ATTEMPTS, NOT_CHECKED, Guard, PlantExhausted
from .mint import (
    CITATION,
    DATE,
    ENTITY,
    FIGURE,
    KINDS,
    LABEL,
    RECIPE,
    TOKEN,
    Minted,
    PlantError,
    mint,
)
from .pipeline import (
    PUBLISHED_DEMO_SEED,
    PlantedCorpus,
    PlantingError,
    plant,
    write_corpus,
)
from .templates import (
    MASK_TOKENS,
    SLOT,
    Slot,
    Template,
    unplanted,
)

__all__ = [
    "CHECKED",
    "CITATION",
    "DATE",
    "ENTITY",
    "FIGURE",
    "Guard",
    "KINDS",
    "LABEL",
    "MASK_TOKENS",
    "MAX_ATTEMPTS",
    "Minted",
    "NOT_CHECKED",
    "PUBLISHED_DEMO_SEED",
    "PlantError",
    "PlantExhausted",
    "PlantedCorpus",
    "PlantingError",
    "RECIPE",
    "SLOT",
    "Slot",
    "TOKEN",
    "Template",
    "mint",
    "plant",
    "unplanted",
    "write_corpus",
]
