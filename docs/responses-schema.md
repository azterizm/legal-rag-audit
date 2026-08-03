# `responses.v2` — producing the response file yourself

You do not have to run our code.

The diagnostic needs one file: a JSONL record of what your system answered to each
question. How you produce it is your business. Your own evaluation harness, a QA script,
thirty lines of `curl` and `jq` — all of them are fine, and none of them are worse than
using our `generate` mode. Scoring cannot tell the difference and does not need to.

Two things follow from that, and both are in your favour.

**The security review disappears.** If none of our code runs on your infrastructure,
there is nothing of ours to review. The question stops being asked rather than being
answered at length.

**The evidence is yours.** Findings drawn from responses you generated cannot later be
dismissed as *"their harness prompted it wrong"*. That cuts both ways, deliberately:
it also means a clean result is one you produced.

---

## The shape

One JSON object per line. No enclosing array, no pretty-printing — a record that spans
several lines is the most common way this file comes back malformed, so pipe through
`jq -c` rather than `jq`.

```json
{"schema":"responses.v2","run_id":"b4f1","probe_id":"cit-014","pass_index":1,"query":"What is the indemnity cap in the Northbrook services agreement?","tenant":"tenant_a","answer":"The indemnity is capped at £4,471,203.17 under clause 9.2 …","citations":["doc_7781","doc_7783"],"retrieved_chunks":[{"doc_id":"doc_7781","text":"…"}],"ttfb_ms":812,"total_ms":4310,"http_status":200,"error":null,"started_at":"2026-08-04T09:03:11Z"}
```

Print the authoritative JSON Schema with:

```bash
legal-rag-audit schema --print responses.v2
```

### Fields

| Field | Required | Notes |
|---|---|---|
| `schema` | yes | Exactly `"responses.v2"`. A file that does not declare its contract is refused, not guessed at. |
| `run_id` | yes | Any opaque string, the same on every line of one run. We never parse it. |
| `probe_id` | yes | From the probe file. Must match exactly. |
| `pass_index` | no | 1-based, defaults to 1. Increment it when you ask the same probe again. |
| `query` | yes | The text you actually sent. |
| `tenant` | no | Which tenant identity issued the query, if the probe named one. |
| `answer` | yes | **Verbatim.** May be empty. See below. |
| `citations` | no | `null` and `[]` mean different things. See below. |
| `retrieved_chunks` | no | `[{"text": "…", "doc_id": "…"}]`. Extra keys per chunk are kept. |
| `ttfb_ms`, `total_ms` | no | Integers, milliseconds. |
| `http_status` | no | Integer. |
| `error` | no | Non-null means this record carries no result. See below. |
| `started_at` | no | ISO 8601. |
| `raw_response` | no | Anything you want preserved that has no field of its own. |

Any key outside this list is rejected with a message naming it. That is deliberate: a
typo like `retrieved_chunk` would otherwise be read as *no chunks captured*, quietly
downgrading a check rather than telling you about it at your desk.

---

## Three rules that decide what the report can say

### 1. `answer` must be verbatim

Not summarised, not trimmed, not stripped of markup that was in the original. The Tier 1
checks are exact matches against strings we planted; a truncated answer measures the
truncation. If you must redact something before it leaves your environment, tell us which
probes were touched — those become `NOT_CAPTURED` rather than silently scored.

### 2. `null` and `[]` are different facts

For `citations` and `retrieved_chunks`:

* `null` — **we did not capture this.** The checks that read it are reported as
  `NOT_CAPTURED`.
* `[]` — **captured, and the system returned none.** That is a result, and it is scored.

Collapsing the two is how *"citations were not recorded"* becomes *"the system cited
nothing"*, which is a finding that would have to be withdrawn. If your transport cannot
surface chunks at all, leave the field out entirely and say so in the header below.

### 3. A failed request is not an answer

If a probe timed out, was rate-limited, or returned a 500, record it:

```json
{"schema":"responses.v2","run_id":"b4f1","probe_id":"cit-014","query":"…","answer":"","error":"ReadTimeout after 60s","http_status":null}
```

Every check reads a record with `error` set as `NOT_CAPTURED`. None reads it as a
failure. An empty string with no `error` is a different claim — it says the system was
asked and returned nothing — so do not use it for transport problems.

---

## The header line (recommended)

Optional, and if present it must be the first line of the file:

```json
{"schema":"responses.v2","record":"capture_notes","citations_captured":true,"retrieved_chunks_captured":false,"document_ids":["doc_7781","doc_7783"],"notes":"chunks not exposed by our API"}
```

It resolves an ambiguity nothing else can. Without it, a file where every record has
`citations: null` is indistinguishable from one where your system emits no citations at
all — and we would have to guess which, in a document whose whole value is not guessing.

`document_ids` is the list of identifiers your system assigned to the uploaded corpus.
Citation integrity is set membership — *is each identifier the system returned one it
actually issued?* — so with no set there is nothing to test against and the check reports
`NOT_CAPTURED`. If your upload endpoint returns no identifiers, that is worth knowing
before the run rather than after it.

`revision_wait_seconds` is how long you waited between replacing the documents in
`corpus/revision/` and asking the second-phase probes again. It matters because a
superseded value coming back two seconds after a re-upload is a system that has not
finished indexing, and the same value ten minutes later is a cache that never invalidates
— different findings with different severity, and only the elapsed time separates them.
Leave it null if your run had no revision phase; the check then reports what it saw
without claiming to know which of the two it was.

## The two phases

The probe file gives every probe a `phase`: `initial` or `after_revision`. Ask the
`initial` ones against the corpus as first uploaded. Then replace each document in
`corpus/revision/` with its counterpart under the same name, wait, and ask the
`after_revision` ones. Record what you waited in the header.

If you cannot re-upload — no upload endpoint, a read-only index, a policy against it —
**do not ask the `after_revision` probes at all.** Asking them against an unchanged corpus
produces an unchanged answer, and scoring that as a stale index would be a finding
manufactured out of your constraints rather than your system. Records that never arrive
are `NOT_CAPTURED`, which is the true statement.

---

## Worked example

Given a probe file at `probes.jsonl` and an API that takes `{"query": "..."}` and
returns `{"answer": "...", "sources": [...]}`:

```bash
RUN_ID=$(date +%s)

# Header: state what this script can and cannot capture.
jq -nc --argjson ids "$(cat document_ids.json)" \
  '{schema:"responses.v2",record:"capture_notes",
    citations_captured:true,retrieved_chunks_captured:false,
    document_ids:$ids,notes:"curl+jq; retrieval not exposed"}' > responses.jsonl

# One request per probe, one line per response.
while read -r probe; do
  id=$(jq -r '.probe_id' <<<"$probe")
  text=$(jq -r '.text' <<<"$probe")
  start=$(python3 -c 'import time;print(int(time.time()*1000))')

  body=$(curl -sS -X POST "$TARGET_URL/chat" \
    -H "Authorization: Bearer $TARGET_API_KEY" \
    -H 'Content-Type: application/json' \
    --data "$(jq -nc --arg q "$text" '{query:$q}')")

  now=$(python3 -c 'import time;print(int(time.time()*1000))')

  jq -nc --arg id "$id" --arg q "$text" --arg run "$RUN_ID" \
         --argjson ms "$((now - start))" --argjson body "$body" \
    '{schema:"responses.v2",run_id:$run,probe_id:$id,pass_index:1,query:$q,
      answer:($body.answer // ""),
      citations:($body.sources // null),
      total_ms:$ms,http_status:200}' >> responses.jsonl
done < probes.jsonl
```

Check it before sending:

```bash
legal-rag-audit score --responses responses.jsonl --ground-truth /dev/null
```

That will refuse the ground truth, which you do not have — but it parses the response
file first, so any structural problem is reported with a file and line number while you
can still fix it.

---

## What we do with it

We score it offline against a ground-truth manifest whose hash you were given **before**
the run, so the expectations cannot have been fitted to what came back. The report states
every denominator, names every check that did not run and why, and separates what was
measured from what was inferred.

Scoring is local and offline: `score` opens no sockets, and an attempt raises rather than
being quietly allowed. CI asserts it by running the whole route — `plant`, `hash`,
`score` — inside an empty network namespace, where a socket call fails instead of
resolving. The published image that would package this with egress denied does not exist
yet; until it does, the guarantee rests on that namespace test and on `score` importing
nothing from `transport/`.
