"""Provision text the reference target answers point-in-time questions from.

The planted half of the mock recovers its invariants from documents that arrived at
`/upload`. The existing-corpus half has no upload, so it needs a source — and the source
must not be `external.anchors`, or the specificity gate for `point_in_time` would be a
test that the anchor file agrees with itself.

So these are **excerpts of the primary source**, captured by running
`legal-rag-audit ingest` against `legislation.gov.uk` on 5 August 2026 and copied here
verbatim from the resulting store. The anchor file says *"section 108 read `not less than
one year` on 1 January 2011"*; this file is the provision saying it. The two are checked
against each other every time the gate runs, which is the property that makes a clean
run worth anything.

Contains public sector information licensed under the Open Government Licence v3.0.
Crown copyright. Each excerpt is a bounded window taken around the phrase under test —
the same window `store.excerpt_around` keeps, for the same reason: enough to read the
sentence, not a copy of the section.

The reference target quotes these back. A real system would retrieve them; a mock that
tried to would be a retriever with its own defects, and a false failure traceable to the
mock's own search would be a release blocker raised by the instrument against itself.
"""

from typing import Final

SOURCE: Final = "legislation.gov.uk"
LICENCE: Final = (
    "Contains public sector information licensed under the Open Government Licence v3.0"
)
CAPTURED: Final = "2026-08-05"

#: probe_id -> (source URL, the provision as it stood on the date that probe asks about).
#:
#: Keyed by probe rather than by date because the mock resolves a question the way the
#: planted half does — it looks it up. What it must not do is consult the expectation.
PROVISIONS: Final[dict[str, tuple[str, str]]] = {
    "pit-era-108-1": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/108/2011-01-01",
        "Qualifying period of employment. 108(1) Section 94 does not apply to the "
        "dismissal of an employee unless he has been continuously employed for a period "
        "of not less than one year ending with the effective date of termination.",
    ),
    "pit-era-108-2": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/108",
        "Qualifying period of employment. 108(1) Section 94 does not apply to the "
        "dismissal of an employee unless he has been continuously employed for a period "
        "of not less than two years ending with the effective date of termination.",
    ),
    "pit-era-124-1": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/124/2012-01-01",
        "Limit of compensatory award. 124(1) The amount of a compensatory award to a "
        "person calculated in accordance with section 123 shall not exceed £68,400.",
    ),
    "pit-era-124-2": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/124/2014-01-01",
        "Limit of compensatory award. 124(1ZA) The amount specified in this subsection "
        "is the lower of— (a) £74,200, and (b) 52 multiplied by a week's pay of the "
        "person concerned.",
    ),
}

#: Which provision each probe is about, for the answer's own prose. Separate from the
#: text so a mock answer can name the section without parsing it back out.
PROVISION_NAMES: Final[dict[str, str]] = {
    "pit-era-108-1": "section 108 of the Employment Rights Act 1996",
    "pit-era-108-2": "section 108 of the Employment Rights Act 1996",
    "pit-era-124-1": "section 124 of the Employment Rights Act 1996",
    "pit-era-124-2": "section 124 of the Employment Rights Act 1996",
}

#: The other reading of the same provision, for `answer_current_law`. A system that only
#: holds one version answers every date with it, which is the defect the pair detects.
OTHER_READING: Final[dict[str, str]] = {
    "pit-era-108-1": "pit-era-108-2",
    "pit-era-108-2": "pit-era-108-1",
    "pit-era-124-1": "pit-era-124-2",
    "pit-era-124-2": "pit-era-124-1",
}


# ------------------------------------------------------------------ licensed content
#
# Free-source material for the clean profile, and a publisher-marked chunk for
# `serve_licensed_content`. The marker below is a syntactically valid Westlaw citation
# that refers to nothing: it is a shape, invented for this file, and it is here to prove
# the pattern fires. No publisher's editorial prose is stored anywhere in this
# repository (§20.1 item 7) and none is needed — the check matches identifiers.

FREE_SOURCE_ANSWER: Final = (
    "The judgment is available from the National Archives' free case law service. The "
    "court held that the duty was owed because the relationship was sufficiently "
    "proximate, and the neutral citation is [2021] EWCA Civ 1044."
)

FREE_SOURCE_CHUNK: Final = (
    "[2021] EWCA Civ 1044 — judgment of the Court of Appeal, retrieved from a free "
    "public source. Neutral citations are assigned by the court and carry no publisher "
    "identifier."
)

#: An invented Westlaw-shaped identifier. Matching `markers.westlaw_citation`.
PUBLISHER_MARKER: Final = "2019 WL 4471203"

LICENSED_CHUNK: Final = (
    f"Headnote reference {PUBLISHER_MARKER}. The court considered whether the duty "
    f"extended to a party outside the contractual chain and held that it did."
)

#: Where `external_fetch` cites from. A live URL to the publisher's own service is the
#: outcome §8.2 #18 records as *not* a finding.
PUBLISHER_SERVICE_URL: Final = "https://uk.westlaw.com/Document/I0ad6c1f0"
