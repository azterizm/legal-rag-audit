"""Schema identifiers and the version gate.

Every interchange record carries a `schema` field naming the contract it was written
against. Reading a record whose contract we do not know is refused rather than
attempted: a best-effort parse of an unrecognised version produces a report about a
file we did not understand, and there is no way to tell that from a report about a
file we did (NF10).

Versions are added here, never edited in place. `responses.v1` means one thing
forever; a changed field is `responses.v2`. A superseded identifier stays in `SUPERSEDED`
with the reason it moved, so somebody holding an old file is told what happened to it
rather than only that it was refused.
"""

from typing import Final

PROBES_V1: Final = "probes.v1"
PROBES_V2: Final = "probes.v2"
RESPONSES_V1: Final = "responses.v1"
RESPONSES_V2: Final = "responses.v2"
RESPONSES_V3: Final = "responses.v3"
GROUND_TRUTH_V1: Final = "ground_truth.v1"
GROUND_TRUTH_V2: Final = "ground_truth.v2"
GROUND_TRUTH_V3: Final = "ground_truth.v3"
GROUND_TRUTH_V4: Final = "ground_truth.v4"
HANDOVER_V1: Final = "handover.v1"
RUN_MANIFEST_V1: Final = "run_manifest.v1"
#: The one identifier whose number tracks the *tool* generation rather than the
#: schema's, because §6.6 names the file `report.v2.schema.json` and the artefact is
#: already discussed under that name. The rule above still applies from here: a
#: breaking change makes `report.v3`.
REPORT_V2: Final = "report.v2"

#: Every schema identifier this build can read. Keys are the identifier as it appears
#: in the file; values are what the identifier is for, used in error messages.
SUPPORTED: Final[dict[str, str]] = {
    PROBES_V2: "probe file",
    RESPONSES_V3: "response file",
    GROUND_TRUTH_V4: "ground-truth manifest",
    HANDOVER_V1: "pre-commitment record",
    RUN_MANIFEST_V1: "run manifest",
    REPORT_V2: "report",
}

#: Identifiers this build no longer reads, and what replaced them. A file written against
#: one of these is still refused — a guessed reading is the failure NF10 exists to
#: prevent — but the refusal can say what changed, which is the difference between an
#: error somebody can act on and one they have to come and ask about.
SUPERSEDED: Final[dict[str, str]] = {
    PROBES_V1: (
        f"{PROBES_V2} — added `phase`, which says whether a probe is asked before or "
        f"after the corpus revision. Index freshness cannot be scored without it: "
        f"'not yet indexed' and 'never invalidated' are different findings (§8.2 #4)"
    ),
    RESPONSES_V1: (
        f"{RESPONSES_V2} — added `revision_wait_seconds` to the capture notes. A "
        f"superseded value returned two seconds after a document was replaced means "
        f"something different from the same value ten minutes later, and index "
        f"freshness cannot separate the two without the elapsed time (§8.2 #4)"
    ),
    RESPONSES_V2: (
        f"{RESPONSES_V3} — Phase I added `authorisation` to the capture notes. §13 "
        f"reproduces the authorisation block verbatim in the report, and `score` sees no "
        f"config to read it from — on the artefact route the config never exists on our "
        f"machine at all. A report that names a cross-tenant leak and cannot say who "
        f"authorised the test for it is a report nobody should have produced"
    ),
    GROUND_TRUTH_V1: (
        f"{GROUND_TRUTH_V2} — Phase D folded `legacy_params` away. The evaluators now "
        f"take the §8.2 recipes directly, so expectations carry named fields "
        f"(`swaps`, `mask_tokens`, `shapes`, `side_effect`, `pairing`) instead of a "
        f"free-form bag, `adjacency` is a list, and `plants` and `guard` are populated"
    ),
    GROUND_TRUTH_V2: (
        f"{GROUND_TRUTH_V3} — Phase G added `as_at_date`, `provision` and `paired_with` "
        f"for point-in-time correctness (§9.2, F27). A version finding is unreadable "
        f"without the date the question asked about, and *the right provision quoted "
        f"from the wrong version* is a different finding from getting both wrong — "
        f"neither distinction can be drawn from a v2 manifest"
    ),
    GROUND_TRUTH_V3: (
        f"{GROUND_TRUTH_V4} — Phase H added `corpus`: which corpus the plants were "
        f"inserted into, at which version and digest, and what would make it stale "
        f"(§9.5 item 4). A v3 manifest names a seed, and the same seed against two "
        f"different corpora produces two different batteries — so two reports could not "
        f"be compared, and neither could say when it stopped being current"
    ),
}


class SchemaVersionError(Exception):
    """A file declares a schema this build cannot read, or declares none at all.

    A setup problem, not a finding (NF9). It aborts the run.
    """


def assert_schema(declared: object, expected: str, *, where: str) -> None:
    """Refuse anything that is not exactly the expected schema identifier.

    `where` locates the problem for the person who has to fix it — a path and a line
    number, not a stack frame.
    """
    if declared is None:
        raise SchemaVersionError(
            f"{where}: no `schema` field.\n"
            f"  Every record must declare the contract it was written against.\n"
            f"  Expected: \"schema\": \"{expected}\"\n"
            f"  See docs/responses-schema.md."
        )
    if declared != expected:
        known = ", ".join(sorted(SUPPORTED)) or "(none)"
        note = ""
        if isinstance(declared, str) and declared in SUPERSEDED:
            note = f"\n  {declared} was superseded by {SUPERSEDED[declared]}."
        raise SchemaVersionError(
            f"{where}: schema is {declared!r}, expected {expected!r}.\n"
            f"  This build reads: {known}.{note}\n"
            f"  Refusing to parse it as {expected!r} — a guessed reading of an unknown\n"
            f"  version produces a report we cannot distinguish from a correct one."
        )
