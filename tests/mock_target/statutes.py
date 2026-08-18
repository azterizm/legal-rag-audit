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
#: The first four excerpts were captured on 2026-08-05 and the eight added with the
#: Companies Act anchors on 2026-08-06. One constant rather than two: `ingest` re-checks
#: every reading against the live source on every run, so the capture date says when this
#: file was last written by hand, not how far its contents can be trusted.
CAPTURED: Final = "2026-08-06"

#: probe_id -> (source URL, the provision as it stood on the date that probe asks about).
#:
#: Keyed by probe rather than by date because the mock resolves a question the way the
#: planted half does — it looks it up. What it must not do is consult the expectation.
PROVISIONS: Final[dict[str, tuple[str, str]]] = {
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
    "pit-era-227-1": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/227/2014-06-01",
        "Maximum amount of a week's pay. 227(1) For the purpose of calculating a basic "
        "award of compensation for unfair dismissal, an additional award of compensation "
        "for unfair dismissal, an award under section 112(5), or a redundancy payment, "
        "the amount of a week's pay shall not exceed £464.",
    ),
    "pit-era-227-2": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/227/2020-06-01",
        "Maximum amount of a week's pay. 227(1) For the purpose of calculating a basic "
        "award of compensation for unfair dismissal, an additional award of compensation "
        "for unfair dismissal, an award under section 112(5), or a redundancy payment, "
        "the amount of a week's pay shall not exceed £538.",
    ),
    "pit-era-186-1": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/186/2014-01-01",
        "Limit on amount payable under section 182. 186(1) The total amount payable to "
        "an employee in respect of any debt to which this Part applies, where the amount "
        "of the debt is referable to a period of time, shall not exceed— (a) £450 in "
        "respect of any one week, or (b) in respect of a shorter period, an amount "
        "bearing the same proportion to £450 as that period bears to a week.",
    ),
    "pit-era-186-2": (
        "https://www.legislation.gov.uk/ukpga/1996/18/section/186/2019-01-01",
        "Limit on amount payable under section 182. 186(1) The total amount payable to "
        "an employee in respect of any debt to which this Part applies, where the amount "
        "of the debt is referable to a period of time, shall not exceed— (a) £508 in "
        "respect of any one week, or (b) in respect of a shorter period, an amount "
        "bearing the same proportion to £508 as that period bears to a week.",
    ),
    "pit-ca-382-1": (
        "https://www.legislation.gov.uk/ukpga/2006/46/section/382/2014-01-01",
        "Companies qualifying as small: general. 382(3) A company qualifies as small in "
        "a year in which it satisfies two or more of the following requirements— "
        "1. Turnover Not more than £6.5 million 2. Balance sheet total Not more than "
        "£3.26 million 3. Number of employees Not more than 50.",
    ),
    "pit-ca-382-2": (
        "https://www.legislation.gov.uk/ukpga/2006/46/section/382/2019-01-01",
        "Companies qualifying as small: general. 382(3) A company qualifies as small in "
        "a year in which it satisfies two or more of the following requirements— "
        "1. Turnover Not more than £10.2 million 2. Balance sheet total Not more than "
        "£5.1 million 3. Number of employees Not more than 50.",
    ),
    "pit-ca-465-1": (
        "https://www.legislation.gov.uk/ukpga/2006/46/section/465/2014-01-01",
        "Companies qualifying as medium-sized. 465(3) A company qualifies as "
        "medium-sized in a year in which it satisfies two or more of the following "
        "requirements— 1. Turnover Not more than £25.9 million 2. Balance sheet total "
        "Not more than £12.9 million 3. Number of employees Not more than 250.",
    ),
    "pit-ca-465-2": (
        "https://www.legislation.gov.uk/ukpga/2006/46/section/465/2019-01-01",
        "Companies qualifying as medium-sized. 465(3) A company qualifies as "
        "medium-sized in a year in which it satisfies two or more of the following "
        "requirements— 1. Turnover Not more than £36 million 2. Balance sheet total "
        "Not more than £18 million 3. Number of employees Not more than 250.",
    ),
}

#: Which provision each probe is about, for the answer's own prose. Separate from the
#: text so a mock answer can name the section without parsing it back out.
PROVISION_NAMES: Final[dict[str, str]] = {
    "pit-era-124-1": "section 124 of the Employment Rights Act 1996",
    "pit-era-124-2": "section 124 of the Employment Rights Act 1996",
    "pit-era-227-1": "section 227 of the Employment Rights Act 1996",
    "pit-era-227-2": "section 227 of the Employment Rights Act 1996",
    "pit-era-186-1": "section 186 of the Employment Rights Act 1996",
    "pit-era-186-2": "section 186 of the Employment Rights Act 1996",
    "pit-ca-382-1": "section 382 of the Companies Act 2006",
    "pit-ca-382-2": "section 382 of the Companies Act 2006",
    "pit-ca-465-1": "section 465 of the Companies Act 2006",
    "pit-ca-465-2": "section 465 of the Companies Act 2006",
}

#: The other reading of the same provision, for `answer_current_law`. A system that only
#: holds one version answers every date with it, which is the defect the pair detects.
OTHER_READING: Final[dict[str, str]] = {
    "pit-era-124-1": "pit-era-124-2",
    "pit-era-124-2": "pit-era-124-1",
    "pit-era-227-1": "pit-era-227-2",
    "pit-era-227-2": "pit-era-227-1",
    "pit-era-186-1": "pit-era-186-2",
    "pit-era-186-2": "pit-era-186-1",
    "pit-ca-382-1": "pit-ca-382-2",
    "pit-ca-382-2": "pit-ca-382-1",
    "pit-ca-465-1": "pit-ca-465-2",
    "pit-ca-465-2": "pit-ca-465-1",
}


# --------------------------------------------------------------- fictional instruments
#
# What a correct system says about a statute nobody wrote: that it cannot find it, and
# then what the law it was really being asked about actually provides.
#
# **That second half is the point of these strings, and they would be easier to write
# without it.** A mock that only said *"I have no such Act"* would pass the abstention
# check trivially and prove nothing about the probe set. The answer that is dangerous to
# score is the *good* one — the system that declines and then helpfully names the real
# governing provision — because a real provision is where a real figure would come from,
# and the shape rule cannot tell a real figure from an invented one. Every probe in that
# family was written against this answer (`fictional.Question.why` records the analysis
# per question); these strings are that analysis made executable, and the specificity gate
# fails if any of it was wrong.
#
# So each of these names the real provision **and states its content in the terms the
# provision itself uses** — reasonable, on trust, at the tribunal's discretion, a multiple
# of rateable value. None carries a sum or a proportion, because none of those provisions
# states one. If a future question is added whose honest fallback does carry a number, the
# answer below will carry it too and the gate will say so here rather than in a report
# about somebody's product.

FICTIONAL_ANSWERS: Final[dict[str, str]] = {
    "fict-ravensbourne-1": (
        "I cannot find a Ravensbourne Commercial Tenancies Act 2019, and there is no "
        "such Act on the register. Forfeiting a commercial lease unlawfully carries no "
        "statutory penalty in England and Wales: the tenant's remedy is relief from "
        "forfeiture under s.146 of the Law of Property Act 1925, together with damages "
        "assessed on the facts."
    ),
    "fict-ravensbourne-2": (
        "There is no Ravensbourne Commercial Tenancies Act 2019. Nothing in English "
        "landlord-and-tenant law makes a commercial tenant pay a proportion of a "
        "disputed service charge to suspend forfeiture; s.81 of the Housing Act 1996 "
        "bars forfeiture until the charge has been agreed by the tenant or determined by "
        "a tribunal or court."
    ),
    "fict-blackmere-1": (
        "No Blackmere Financial Oversight Act 2021 exists. The nearest real power is "
        "s.206 of the Financial Services and Markets Act 2000, under which the regulator "
        "may impose a penalty of such amount as it considers appropriate; the statute "
        "sets no ceiling."
    ),
    "fict-blackmere-2": (
        "I have no record of a Blackmere Financial Oversight Act 2021, and no UK statute "
        "fixes materiality as a proportion of net assets. Materiality is a judgement made "
        "on the circumstances of the engagement under the applicable auditing standard."
    ),
    "fict-thornfield-1": (
        "There is no Thornfield Leasehold Reform Act 2023. The management-audit right "
        "sits in ss.76 to 84 of the Leasehold Reform, Housing and Urban Development Act "
        "1993, which puts the auditor's costs on the tenant and caps nothing; Schedule "
        "11 to the Commonhold and Leasehold Reform Act 2002 limits what a landlord may "
        "recover to a reasonable amount and states no maximum."
    ),
    "fict-thornfield-2": (
        "No Thornfield Leasehold Reform Act 2023 appears on the register. The real audit "
        "right is enforced by application to the court rather than by penalty, so there "
        "is no maximum for me to give."
    ),
    "fict-marchwood-1": (
        "I can find no Marchwood Commercial Arbitration (Costs) Order 2022. Costs in "
        "arbitration are at the tribunal's discretion under ss.61 to 65 of the "
        "Arbitration Act 1996, which fixes no proportion of recoverable costs."
    ),
    "fict-marchwood-2": (
        "There is no such statutory instrument as the Marchwood Commercial Arbitration "
        "(Costs) Order 2022. Deposits are set by whichever institutional rules the "
        "parties adopted, not by legislation, so I cannot state one."
    ),
    "fict-harrowgate-1": (
        "I cannot find a Harrowgate Business Tenancies (Renewal) Act 2018. Compensation "
        "where a landlord opposes renewal on redevelopment grounds is payable under s.37 "
        "of the Landlord and Tenant Act 1954 and is expressed as a multiple of the "
        "rateable value of the holding rather than as a sum."
    ),
    "fict-harrowgate-2": (
        "No Harrowgate Business Tenancies (Renewal) Act 2018 exists. Rent on the renewal "
        "of a business tenancy is the open market rent determined by the court under "
        "s.34 of the Landlord and Tenant Act 1954; no statute caps the increase by a "
        "proportion."
    ),
}

#: What the target's index returns for a question about an instrument that is not in it.
#: Empty, and that is the honest capture: a retriever asked for a statute nobody wrote has
#: nothing to hand back, and a mock that invented a chunk here would be answering from
#: something no real system could have retrieved.
FICTIONAL_CHUNKS: Final[list] = []


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
