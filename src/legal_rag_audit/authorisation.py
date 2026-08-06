"""Authorisation and the legal boundary, enforced rather than promised (§13, F37).

> Signing up for a product authorises **use**, not **testing**. Most SaaS terms
> separately prohibit benchmarking, automated access and multi-account creation, and
> probing tenant isolation on a system we do not own is a **Computer Misuse Act 1990**
> exposure. *"I signed up for a trial"* is not authorisation.

§16 says that in prose to a reader. This module says it to the program, which is the
difference between a claim about our conduct and a property of the software. A battery
that needs written authorisation and has not been given one does not run — not because an
operator remembered, but because `require()` raised before the first request went out.

## Two things make a run need authorisation, and they are independent

**The families it asks.** §13 classes probe families by what running one actually *does*.
Asking a question and reading the answer is the ordinary use a trial exists for. Planting
an instruction in a document to see whether the retriever obeys it is not, and neither is
asking as one tenant to see whether another tenant's matter comes back.

**Whether it uploads.** A planted battery puts our documents into somebody's index, and
one of those documents carries an injection payload by construction. §16.1 lists
*uploading adversarial documents* in the column headed **never on a self-signed-up
account**, so the upload is an authorised act in its own right, whatever families ride on
it. This is why the existing-corpus half of §9.1 is the free pre-finding: it uploads
nothing, so it clears both tests.

`require()` collects **every** reason rather than the first, because an operator who fixes
one and re-runs into the next has been told the truth twice instead of once.

## Failing closed

An unrecognised family is treated as requiring authorisation. A new check arrives as a
name in a probe file long before anybody thinks about its legal class, and the safe
default for *we have not classified this* is not *ordinary use*. `test_authorisation.py`
asserts every family both batteries ask is classified, so the default is a backstop and
not a habit.

## What this module is not

It is not a legal opinion, and a populated block is not evidence that anybody was
actually authorised — a determined operator can type a name into a YAML file. What it
does is make the crossing **deliberate and recorded**: someone has to write down who
authorised what, on what date, in which environment, and that text is reproduced verbatim
in the report. An accident cannot produce it, and a misrepresentation is on the record.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The two classes in §13's table.
ORDINARY: Final = "ordinary_use"
AUTHORISED: Final = "authorised_testing"

#: The environments a run may declare. `production` is the one that needs a second,
#: separate act — see `PRODUCTION_ACK`.
ENVIRONMENTS: Final[tuple[str, ...]] = ("dev", "sandbox", "staging", "production")

PRODUCTION: Final = "production"

#: The flag name, as the operator types it. Long and unpleasant on purpose: it has to be
#: the kind of thing nobody puts in a shell alias without noticing.
PRODUCTION_ACK: Final = "--i-have-written-authorisation-for-production"


class AuthorisationError(Exception):
    """A run needs written authorisation it has not been given.

    A setup problem, not a finding (NF9). It aborts before any request is sent — the
    point of the control is that the thing does not happen, not that it is reported after
    it has.
    """


@dataclass(frozen=True)
class FamilyClass:
    """One probe family and what running it actually does.

    `because` is written for the person reading an abort message at nine at night, and it
    describes the *act*, not the check. "Tests injection resistance" tells an operator
    nothing about why consent is needed; "plants an instruction in a document and tests
    whether the retriever obeys it" tells them exactly what they would be doing to
    somebody else's system.
    """

    family: str
    requires: str
    because: str


#: §13's table, per family. The families are the ones `probes.battery` and
#: `external.battery` actually ask; a test asserts this covers both.
FAMILIES: Final[tuple[FamilyClass, ...]] = (
    # ---------------------------------------------------------------- ordinary use
    FamilyClass(
        "unsupported_assertions",
        ORDINARY,
        "asks a question and reads the answer",
    ),
    FamilyClass(
        "citation_integrity",
        ORDINARY,
        "checks whether the authorities an answer cites resolve to real ones",
    ),
    FamilyClass(
        "abstention",
        ORDINARY,
        "asks a question the corpus cannot answer and reads what comes back",
    ),
    FamilyClass(
        "parametric_bleed",
        ORDINARY,
        "asks about a topic outside the corpus",
    ),
    FamilyClass(
        "point_in_time",
        ORDINARY,
        "asks what a provision said on a date, against public legislation",
    ),
    FamilyClass(
        "licensed_content_reproduction",
        ORDINARY,
        "reads an answer for publisher editorial markers. No upload, no second "
        "account, no automation — the exception §16.2 grants, and it earns it",
    ),
    FamilyClass(
        "response_divergence",
        ORDINARY,
        "asks the same question more than once and compares the answers",
    ),
    FamilyClass(
        "retrieval_relevance",
        ORDINARY,
        "scores chunks the target already returned",
    ),
    # ------------------------------------------------------------ authorised testing
    FamilyClass(
        "injection_resistance",
        AUTHORISED,
        "plants an instruction inside a document and tests whether the retriever "
        "obeys it. This is an attempt to subvert an instruction boundary on somebody "
        "else's system",
    ),
    FamilyClass(
        "cross_tenant_leakage",
        AUTHORISED,
        "queries as one tenant to see whether another tenant's matter comes back. It "
        "needs two accounts, and probing isolation on a system we do not own is a "
        "Computer Misuse Act 1990 exposure",
    ),
    FamilyClass(
        "index_freshness",
        AUTHORISED,
        "replaces a document in the target's index mid-run and asks again",
    ),
    # The rest of the planted battery. Each of these is a perfectly ordinary question
    # *asked of documents we put there*, which is why they sit in this column: the act
    # needing consent is the upload, and `upload_requires_authorisation()` says so
    # separately. They are classed here too so that a probe file arriving on its own —
    # the artefact route, §5.1.1 — is classified correctly without a config to read.
    FamilyClass(
        "contradiction_surfacing",
        AUTHORISED,
        "needs a planted pair of documents that disagree, uploaded to the index",
    ),
    FamilyClass(
        "routing_contamination",
        AUTHORISED,
        "needs a namespace-scoped document uploaded, and asks whether a query scoped "
        "elsewhere reaches it",
    ),
    FamilyClass(
        "clause_synthesis",
        AUTHORISED,
        "needs a planted obligation and its planted exclusion in the index",
    ),
    FamilyClass(
        "context_memory",
        AUTHORISED,
        "needs planted referents in the index",
    ),
    FamilyClass(
        "disambiguation",
        AUTHORISED,
        "needs the planted pair of instruments with overlapping numbering",
    ),
    FamilyClass(
        "structural_integrity",
        AUTHORISED,
        "needs the planted nested document in the index",
    ),
    FamilyClass(
        "entity_masking",
        AUTHORISED,
        "needs planted counterparties in the index, and reads answers for the "
        "target's own masking placeholders",
    ),
    FamilyClass(
        "attribution",
        AUTHORISED,
        "needs the planted pair in the index and scores which document each fact is "
        "attached to",
    ),
    FamilyClass(
        "latency",
        AUTHORISED,
        "times a planted contradictory question against a planted baseline",
    ),
)

BY_FAMILY: Final[dict[str, FamilyClass]] = {f.family: f for f in FAMILIES}

#: What an unrecognised family is treated as. Not a fallback to be relied on — see the
#: module docstring — but the direction a gap has to fail in.
UNCLASSIFIED: Final = FamilyClass(
    "",
    AUTHORISED,
    "is not classified in §13. An unclassified family is treated as needing "
    "authorisation, because the safe reading of *nobody has decided* is not *this is "
    "ordinary use*",
)

#: Why uploading is itself an authorised act, as the abort message puts it.
UPLOAD_REASON: Final = (
    "this run uploads documents into the target's index, and one of them carries an "
    "injection payload by construction. §16.1 puts *uploading adversarial documents* in "
    "the column headed never on a self-signed-up account. If you cannot obtain written "
    "authorisation, `corpus.mode: existing` probes the target's own index, uploads "
    "nothing, and needs none of this (§9.1, F25)"
)


def classify(family: str) -> FamilyClass:
    """This family's class, failing closed on one nobody has classified."""
    known = BY_FAMILY.get(family)
    if known is not None:
        return known
    return FamilyClass(family, UNCLASSIFIED.requires, UNCLASSIFIED.because)


def authorised_testing(families: Iterable[str]) -> list[FamilyClass]:
    """The families in this battery that need written authorisation, in §13's order."""
    asked = set(families)
    found = [f for f in FAMILIES if f.family in asked and f.requires == AUTHORISED]
    unknown = sorted(asked - set(BY_FAMILY))
    return found + [classify(family) for family in unknown]


# --------------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------------


class Authorisation(BaseModel):
    """Who authorised what, on what date, in which environment.

    Travels with the run and is reproduced **verbatim** in the report manifest, so the
    artefact carries its own provenance of consent (§13 rule 3). A report that names a
    cross-tenant leak and cannot say who authorised the test for it is a report nobody
    should have produced.
    """

    model_config = ConfigDict(extra="forbid")

    #: Name and role. Both, because a name alone does not establish that the person could
    #: give the authorisation.
    authorised_by: str
    authorised_on: date
    environment: Literal["dev", "sandbox", "staging", "production"]
    #: What was authorised, in the authoriser's terms. Free text on purpose: an enum
    #: would let a scope be acknowledged by ticking a box somebody else wrote.
    scope_ack: str
    #: Where the written authorisation lives — an engagement letter, a ticket, an email
    #: reference. Optional, because the tool cannot verify it either way, and a required
    #: field that cannot be checked invites a plausible-looking value.
    reference: Optional[str] = None

    @field_validator("authorised_by", "scope_ack")
    @classmethod
    def _substantive(cls, value: str) -> str:
        text = value.strip()
        if len(text) < 3:
            raise ValueError(
                "must say something. This is reproduced verbatim in the report, where a "
                "reader will use it to decide whether the run should have happened."
            )
        return text

    @field_validator("authorised_on")
    @classmethod
    def _not_in_the_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError(
                f"is in the future ({value.isoformat()}). An authorisation dated after "
                f"the run it authorises is a typo or a backdating attempt, and the "
                f"report would carry it either way."
            )
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == PRODUCTION

    def age_days(self, today: Optional[date] = None) -> int:
        """How old this authorisation was on the day of the run.

        Recorded, not gated. Any expiry we invented would be the `0.85` problem again —
        a number of ours presented as a standard (F24). A reader deciding whether a
        two-year-old scope still covers this run is doing something no threshold can do
        for them, and the number is what lets them do it.
        """
        return ((today or date.today()) - self.authorised_on).days

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# --------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Requirement:
    """One reason this run needs written authorisation."""

    what: str
    because: str


def reasons(
    families: Iterable[str], *, uploads: bool = False
) -> list[Requirement]:
    """Every reason this run needs authorisation, in the order they should be read.

    Empty means the run is ordinary use and needs no block — which is what makes
    `validate` and the existing-corpus battery free (§13 rules 1 and 4).
    """
    found = [
        Requirement(f"the `{f.family}` family", f.because)
        for f in authorised_testing(families)
    ]
    if uploads:
        found.insert(0, Requirement("uploading a corpus", UPLOAD_REASON))
    return found


def require(
    authorisation: Optional[Authorisation],
    families: Iterable[str],
    *,
    uploads: bool = False,
    production_ack: bool = False,
) -> Optional[Authorisation]:
    """Refuse a run that needs written authorisation and has not been given one.

    Returns the block so a caller can record it, or None where none was needed. Raises
    `AuthorisationError` with every reason named, because an operator who fixes one and
    runs into the next has been told the truth twice instead of once.
    """
    needed = reasons(families, uploads=uploads)

    if needed and authorisation is None:
        lines = [
            "This run needs written authorisation and the config declares none.",
            "",
            "Why:",
        ]
        for requirement in needed:
            lines.append(f"  - {requirement.what} {requirement.because}.")
        lines += [
            "",
            "Signing up for a product authorises use, not testing. If you have written",
            "authorisation, record it — it is reproduced verbatim in the report, so the",
            "artefact carries its own provenance of consent:",
            "",
            "  authorisation:",
            '    authorised_by: "Name, Role"',
            f'    authorised_on: "{date.today().isoformat()}"',
            '    environment: "staging"      # dev | sandbox | staging | production',
            '    scope_ack: "injection, canary and upload probes authorised in writing"',
            '    reference: "engagement letter 2026-03, clause 4"   # optional',
        ]
        raise AuthorisationError("\n".join(lines))

    if authorisation is None:
        return None

    if authorisation.is_production and not production_ack:
        raise AuthorisationError(
            f"The authorisation block declares `environment: production`, and there is "
            f"no config-only path to a production run (§13 rule 2).\n"
            f"  Pass {PRODUCTION_ACK} on the command line as well.\n"
            f"  Two acts, deliberately: a config is copied between runs and a command "
            f"line is typed for one. If this is not a production system, correct the "
            f"environment rather than passing the flag."
        )

    return authorisation
