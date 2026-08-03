"""A small bundled register of real parties, and an honest note about its size.

The collision guard has to answer *"could this generated citation resolve to an actual
authority?"* — because the finding it supports is *"your system cited a case that does
not exist"*, and that finding dies the instant somebody produces the case. §20.2 lists
this as a live risk with a two-part mitigation: the guard, plus manual review of the
generated citations in the first corpus of each domain.

What the register can do is catch the coined word that happens to land on a name every
lawyer in the jurisdiction recognises. What it cannot do is stand in for the law reports.
Scoring is offline by construction (§5.1) — no lookup leaves the machine — so there is no
version of this file that closes the gap, and pretending otherwise would be the exact
failure mode this project measures in other people's systems.

So: the register is deliberately modest, its scope is written into every ground-truth
manifest through `guard.NOT_CHECKED`, and the report says which checks were performed.
A reader can then judge the residual risk instead of inheriting our confidence about it.

Matching is on the coined *word* — `Marrentine` — not the assembled citation, and it is
case-insensitive and whole-word. Substring matching would reject a coined word for
containing "Lee" and quietly shrink the generator's range for no gain.
"""

from typing import Final

#: Parties in authorities a legal RAG system is likely to have seen, plus surnames common
#: enough that a coined one landing on them would be unfortunate. Not a database of case
#: law and not presented as one.
REAL_PARTIES: Final[frozenset[str]] = frozenset(
    name.lower()
    for name in (
        # Authorities most likely to be in a general legal corpus or a model's weights.
        "Donoghue", "Stevenson", "Carlill", "Rylands", "Fletcher", "Salomon",
        "Caparo", "Dickman", "Hadley", "Baxendale", "Pepper", "Hart",
        "Anns", "Merton", "Hedley", "Byrne", "Heller", "Partners",
        "Photo", "Securicor", "Williams", "Roffey", "Stilk", "Myrick",
        "Foakes", "Beer", "Pinnel", "Central", "Trees", "Gilbert",
        "Ashe", "Bettini", "Gye", "Poussard", "Spiers", "Bond",
        "Wagon", "Mound", "Overseas", "Tankship", "Miller", "Jackson",
        "Sturges", "Bridgman", "Hunter", "Canary", "Wharf", "Cambridge",
        "Bolam", "Bolitho", "Montgomery", "Lanarkshire", "Barnett", "Chelsea",
        "Wednesbury", "Padfield", "Ridge", "Baldwin", "Datafin", "Factortame",
        "Pinochet", "Belmarsh", "Miller", "Cherry", "Evans", "Rahmatullah",
        # Surnames common enough to be someone's actual name in an English report.
        "Smith", "Jones", "Brown", "Taylor", "Wilson", "Davies", "Evans",
        "Thomas", "Johnson", "Roberts", "Walker", "Wright", "Robinson",
        "Thompson", "White", "Hughes", "Edwards", "Green", "Lewis", "Wood",
        "Harris", "Martin", "Jackson", "Clarke", "Clark", "Turner", "Hill",
        "Scott", "Cooper", "Morris", "Ward", "Moore", "King", "Watson",
        "Baker", "Harrison", "Morgan", "Patel", "Khan", "Ahmed", "Singh",
        "Murphy", "Kelly", "O'Brien", "Byrne", "Ryan", "Sullivan", "Walsh",
        "MacDonald", "Campbell", "Stewart", "Anderson", "Mitchell", "Fraser",
    )
)

#: Words a coined proper noun must not be, for reasons other than being a real party:
#: they are load-bearing vocabulary in the documents the plants sit in, so a plant that
#: matched one would fire on ordinary prose rather than on our token.
RESERVED: Final[frozenset[str]] = frozenset(
    word.lower()
    for word in (
        "clause", "schedule", "annex", "article", "section", "party", "parties",
        "agreement", "contract", "liability", "indemnity", "warranty", "tier",
        "band", "matter", "client", "tenant", "supplier", "customer", "vendor",
        "statute", "regulation", "provision", "obligation", "exclusion",
    )
)


def is_real_party(word: str) -> bool:
    """Whether a coined word collides with the bundled register."""
    lowered = word.strip().lower()
    return lowered in REAL_PARTIES or lowered in RESERVED
