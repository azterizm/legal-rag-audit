"""Schema identifiers and the version gate.

Every interchange record carries a `schema` field naming the contract it was written
against. Reading a record whose contract we do not know is refused rather than
attempted: a best-effort parse of an unrecognised version produces a report about a
file we did not understand, and there is no way to tell that from a report about a
file we did (NF10).

Versions are added here, never edited in place. `responses.v1` means one thing
forever; a changed field is `responses.v2`.
"""

from typing import Final

PROBES_V1: Final = "probes.v1"
RESPONSES_V1: Final = "responses.v1"
GROUND_TRUTH_V1: Final = "ground_truth.v1"

#: Every schema identifier this build can read. Keys are the identifier as it appears
#: in the file; values are what the identifier is for, used in error messages.
SUPPORTED: Final[dict[str, str]] = {
    PROBES_V1: "probe file",
    RESPONSES_V1: "response file",
    GROUND_TRUTH_V1: "ground-truth manifest",
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
        raise SchemaVersionError(
            f"{where}: schema is {declared!r}, expected {expected!r}.\n"
            f"  This build reads: {known}.\n"
            f"  Refusing to parse it as {expected!r} — a guessed reading of an unknown\n"
            f"  version produces a report we cannot distinguish from a correct one."
        )
