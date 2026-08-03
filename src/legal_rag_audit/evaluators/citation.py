"""3 — Citation integrity (§8.2 #3, Tier 1).

Set membership, which is why it is Tier 1: the target itself issued the document
identifiers at upload, so *"is this one of yours"* has an answer neither side has to
interpret. Three counters, kept apart because they carry entirely different weight.

**(a) `unresolvable_citations`** — a cited identifier that is not in the upload manifest.
The system pointed at a document that does not exist in its own index. Counted.

**(b) `non_existent_authorities`** — a cited authority that is in no version of the
corpus and is not a real case. Sanction class, one instance sufficient (§3.4). **Not
scored here, and the report says so rather than omitting it.** Establishing that an
authority does not exist requires a register of real authorities; ours is a few dozen
names (`plants.register`) bundled to keep generated citations off real ones, not a
substitute for the law reports. Scoring against it would fail a system that correctly
cited an authority we had not heard of — a false positive, which §14.2 makes a release
blocker, and one that alleges fabrication against a named company. The external ground
truth this needs arrives with Phase G.

**(c) `citation_misattribution`** — a cited identifier that *is* in the manifest, but the
document behind it carries none of the plants the probe required. The citation resolves
and supports nothing. Scored as set membership against `must_cite_any_of`: the ground
truth names the documents that actually contain the required invariants, so a probe that
cites only others has attributed its answer to the wrong file.
"""

from typing import Any

from ._common import FAIL, PASS, normalise, result

#: Why counter (b) is absent from every result, printed rather than implied.
NOT_SCORED_REASON = (
    "non_existent_authorities is not scored: deciding that a cited authority does not "
    "exist needs a register of real authorities, which is external ground truth arriving "
    "in Phase G. The bundled register exists to keep generated citations off real ones "
    "and is far too small to support the opposite claim — scoring against it would "
    "manufacture an allegation of fabrication out of our own incomplete data"
)


def _identifier(citation: Any) -> str:
    if isinstance(citation, dict):
        for key in ("id", "doc_id", "document_id", "source"):
            if key in citation:
                return str(citation[key])
    return str(citation)


class CitationEvaluator:
    """Cited identifiers against the manifest the target itself issued."""

    def evaluate(
        self,
        returned_citations: list[Any],
        valid_document_ids: set[str],
        must_cite_any_of: list[str] = (),
    ) -> dict[str, Any]:
        cited = [_identifier(c) for c in returned_citations or []]
        known = {normalise(d) for d in valid_document_ids or set()}

        unresolvable = [c for c in cited if normalise(c) not in known]
        resolvable = [c for c in cited if normalise(c) in known]

        required = {normalise(d) for d in must_cite_any_of or []}
        # Only meaningful when the ground truth names the documents that hold the
        # invariants. With none named there is nothing to be misattributed *to*, and a
        # counter that fired anyway would be measuring the absence of our own data.
        misattributed: list[str] = []
        if required and resolvable:
            if not any(normalise(c) in required for c in resolvable):
                misattributed = list(resolvable)

        failures = unresolvable + misattributed

        return result(
            FAIL if failures else PASS,
            appeared=failures,
            unresolvable_citations=unresolvable,
            citation_misattribution=misattributed,
            non_existent_authorities=None,
            non_existent_authorities_not_scored=NOT_SCORED_REASON,
            total_citations=len(cited),
            manifest_size=len(known),
            required_documents=list(must_cite_any_of or []),
        )
