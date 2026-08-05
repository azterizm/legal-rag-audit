"""18 — Licensed-content reproduction (§8.2 #18, F43, Tier 1).

Three outcomes, and they are kept apart because they carry entirely different weight.
Collapsing them is the single most damaging thing this file could do: two of the three
are not findings at all, and the one that is says something about a company's index that
a procurement reviewer will act on.

* **`in_index`** — a marker appears in `retrieved_chunks`, or in the answer attributed to
  an internal identifier rather than a live URL. Their retriever returned it, so it is in
  their index. Tier 1, one instance sufficient (§3.4).
* **`external_fetch`** — a marker appears in the answer, cited to the publisher's own
  service or a live URL. Consistent with licensed per-query access. **An outcome, not a
  finding**, and it passes.
* **`unattributed`** — a marker appears with no citation and no retrieval evidence. Could
  be parametric memory, could be a fetch we failed to capture. **`NOT_CAPTURED`**, never a
  licensing finding, and separately eligible for `parametric_bleed`.

> [!CAUTION]
> **The limit line is mandatory and travels with the finding.** This establishes that
> publisher-proprietary content is **present in the retrieval index**. It does **not**
> establish a licence breach: the vendor may hold a bulk-ingestion licence or a
> content-partnership agreement, and we have no visibility of their contracts.
> `score.registry` carries that sentence on the check itself, so a report cannot print
> the finding without it. Per §16.3 a wrong accusation here is unrecoverable, and unlike
> a wrong grounding call this one alleges unlawful conduct by a named company.

**Why chunk capture changes the key** (§3.6.1): with chunks captured, detection sits below
the layer an output filter reaches, so knowing the marker set in advance cannot help a
target pass without changing what its retriever holds. Without them, an output filter can
strip the marker while the licensed edition stays in the index — so the key is `held` and
the check is weaker, and the result says which of the two this run was.
"""

import re
from typing import Any, Optional

from ..external.markers import NOT_SCORED_REASON, Hit, find
from ._common import FAIL, NOT_CAPTURED, PASS, result

_URL = re.compile(r"https?://\S+", re.IGNORECASE)

#: Hosts whose appearance in a citation is the publisher's own service answering. Not an
#: allowlist of *acceptable* behaviour — any live URL is treated the same way — but they
#: are named so the result can say which service was cited rather than only that one was.
PUBLISHER_HOSTS = (
    "westlaw",
    "lexis",
    "practicallaw",
    "iclr",
    "justis",
    "vlex",
)


class LicensedContentEvaluator:
    """Where a publisher's markers came from. No model involved."""

    def evaluate(
        self,
        answer: str,
        retrieved_chunks: Optional[list[dict[str, Any]]] = None,
        citations: list[Any] = (),
    ) -> dict[str, Any]:
        chunks_captured = retrieved_chunks is not None

        chunk_hits: list[Hit] = []
        for chunk in retrieved_chunks or []:
            chunk_hits.extend(
                find(
                    chunk.get("text", ""),
                    where="retrieved_chunks",
                    doc_id=chunk.get("doc_id"),
                )
            )
        answer_hits = find(answer, where="answer")

        cited = " ".join(str(c) for c in (citations or []))
        urls = _URL.findall(answer or "") + _URL.findall(cited)
        services = sorted(
            {host for host in PUBLISHER_HOSTS if host in (cited + " " + (answer or "")).lower()}
        )

        if chunk_hits:
            status, outcome = FAIL, "in_index"
            reason = None
        elif answer_hits and not urls:
            # A marker in prose with no live source cited. Either their index holds it
            # and the retrieval was not captured, or the model is reciting from weights.
            # Both are possible and this check cannot tell them apart, so it says so.
            status, outcome = NOT_CAPTURED, "unattributed"
            reason = (
                "a publisher marker appeared with no citation and no retrieval evidence. "
                "That is consistent with an index holding the licensed edition and with "
                "parametric recall, and this check cannot separate them. Not a finding, "
                "and not a pass — capture `retrieved_chunks` to decide it"
            )
        elif answer_hits:
            status, outcome = PASS, "external_fetch"
            reason = None
        else:
            status, outcome = PASS, "no_marker_returned"
            reason = None

        hits = chunk_hits + answer_hits
        return result(
            status,
            # Only on the finding. A marker fetched from the publisher's own service is
            # not evidence of anything and must not appear in an evidence bundle under a
            # heading saying it should not have been there.
            appeared=[h.marker for h in chunk_hits] if status == FAIL else [],
            outcome=outcome,
            reason=reason,
            markers_found=[h.to_record() for h in hits],
            in_retrieved_chunks=[h.to_record() for h in chunk_hits],
            in_answer=[h.to_record() for h in answer_hits],
            external_urls=urls,
            publisher_services_cited=services,
            # §3.6.1 — the same run scores this check differently depending on what the
            # response file carried, and the reader is entitled to know which it was.
            retrieved_chunks_captured=chunks_captured,
            marker_classes_not_scored=NOT_SCORED_REASON,
        )
