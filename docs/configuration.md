# Configuration

Mapping the harness to your API's exact shape. This is the reference for `config.yaml` —
every field, the four transport shapes it supports, and the ways each one can be silently
wrong.

> [!IMPORTANT]
> **An incorrect JSONPath is the documented leading cause of false positives.** An empty
> extracted string scored as a finding is a result that has to be retracted in front of a
> buyer. `legal-rag-audit validate -c config.yaml` exists to catch that before a battery
> is ever fired, and it takes two minutes.

---

## The file

```yaml
target:
  name: "vendor-staging"          # local only — never written to any artefact
  pseudonym: null                 # what the report calls it. null keeps it anonymous
  endpoints:
    chat: "https://staging.example.com/api/v1/chat"
    upload: "https://staging.example.com/api/v1/documents"
    retrieval: "https://staging.example.com/api/v1/search"   # optional
  auth:
    type: "bearer"                 # bearer | api_key | basic | cookie | none
    token_env: "TARGET_API_KEY"    # env var only, never inline
  response_format:
    answer_field: "response.text"
    citations_field: "response.sources"
    stream: false                  # true for Server-Sent Events

corpus:
  mode: "planted"                  # plant a seeded corpus (default) | existing
  library: null                    # which corpus from the library — null uses bundled-demo
  seed: null                       # null uses the published demo seed — read the caveat below
  path: "./planted-corpus"         # where the planted corpus is written
  revision_wait_seconds: 60        # wait between replacing a document and re-asking

battery:
  passes: 3                        # ask each probe N times; 1 reports no reproducibility

tests:
  hallucination_rate: true
  citation_integrity: true
  retrieval_relevance: true
  injection_resistance: true
  cross_tenant_leakage: false      # only with a multi-tenant config
  confidence_threshold: true
  contradiction_surfacing: true
  routing_contamination: true
  cross_clause_synthesis: true
  memory_management: true
  cache_invalidation: true
  latency_penalty: true
  retrieval_disambiguation: true
  structural_integrity: true
  entity_masking_rehydration: true
  parametric_knowledge_bleed: true
  cross_document_attribution: true

thresholds:
  max_hallucination_rate: 0.02
  min_retrieval_relevance: 0.85
  max_injection_success_rate: 0.0
  max_cross_tenant_leaks: 0
```

> **`thresholds` are settings, not standards.** `0.85` and `0.02` are numbers someone put
> in a config file. They are not a published benchmark and nothing about them is
> authoritative. Every Tier 2 result is reported as a **distribution with the line
> marked** rather than a bare pass/fail, and the report states where each number came
> from. Presenting a setting as a standard is the exact failure this project exists to
> measure in other people's systems. The `display_thresholds` rename that makes the
> misuse harder to commit by accident is still to come.
>
> Two of the three thresholds now govern nothing: `max_injection_success_rate` and
> `max_cross_tenant_leaks` are Tier 1 counts where one instance is sufficient (§3.4), so
> there is no line to set. They are still read for backward compatibility and are not
> consulted. `abstention` had a fourth, hard-coded at `0.5` inside a cross-encoder; the
> Tier 1 rewrite removed both the model and the number.

## Endpoints

1. **`chat` (required)** — `POST` with the query in a JSON body; returns the answer string
   and, if the system emits them, an array of citations. Extraction is driven by
   `response_format.answer_field` and `citations_field`.
2. **`upload` (required for planted-corpus mode)** — `POST` with document content; the
   harness captures the returned document `id` to build the upload manifest. Citation
   integrity is set membership against that manifest, so without an `id` the check
   silently loses its ground truth.
3. **`retrieval` (optional)** — direct search endpoint. Without it, retrieval relevance
   has no chunks to score and reports `NOT_CAPTURED` rather than passing.

## Authentication

`auth.token_env` names an environment variable and never holds a value. A credential in a
config file is a credential in a diff, in a backup and in whatever the file was copied
into.

| `type` | What the harness sends |
|---|---|
| `bearer` | `Authorization: Bearer <value>` |
| `api_key` | `x-api-key: <value>` |
| `basic` | `Authorization: Basic <value>` |
| `cookie` | **`Cookie: <value>`, verbatim** |
| `none` | nothing |

> [!WARNING]
> **For `cookie`, capture the header, not the token.** The value becomes the entire
> `Cookie:` header exactly as given, so a bare JWT produces `Cookie: eyJhbGci…` — which
> names no cookie and authenticates nothing. What belongs in the variable is the whole
> string the browser sends: `auth_token=eyJhbGci…; auth_check=1`. Getting this wrong
> costs a run: every request returns 401 instantly, `generate` records transport errors
> rather than answers, and nothing distinguishes it from a target that was down. `validate`
> catches it in three probes, which is the reason to run it first.

## Non-standard shapes

Endpoints may be objects rather than strings when you need a specific method, custom
headers, or a nested (or stringified) JSON body. A **`receive`** endpoint handles
decoupled asynchronous responses — the harness triggers generation on `chat` and listens
on `receive`. Use `{{QUERY}}` in `body`; for uploads, `{{FILENAME}}` and `{{CONTENT}}`.

```yaml
target:
  endpoints:
    chat:
      url: "https://app.example.com/v1/api_core/widget/send_message/?language=en"
      method: "POST"
      headers:
        accept: "application/json, text/plain, */*"
        conv-id: "bd208096-772e-40a7-bcde-702ad8bdebfc"
      body: '{"content":"{{QUERY}}","is_voice":false,"client_message_id":"f9517177-f80c"}'
    receive:
      # wss:// is detected as a WebSocket
      url: "wss://app.example.com/socket.io/?EIO=4&transport=websocket"
      headers:
        accept-language: "en-GB,en-US;q=0.9,en;q=0.8"
      # Connection init packet. Accepts a string ("40" for Socket.IO) or a JSON object.
      init_message: "40"
  response_format:
    answer_field: "$[?(@.event_type=='message' & @.data.author.type=='ai_assistant')].data.content"
    stream: true
    stop_payload_match: "MESSAGE_END"
```

A config of this shape has four independent ways to be silently wrong — the handshake
frame, the terminator, and the two JSONPaths — and none of them fails loudly. Run
`legal-rag-audit validate -c config.yaml` once after writing it. It prints the frames it
received, so a terminator can be chosen from what the target actually sends rather than
from what its documentation says it sends.

## Streams that interleave reasoning with the answer

A JSONPath cannot ask what *type* of frame it is looking at: `jsonpath_ng` filters apply
to arrays, and one SSE frame is a dict. On a target that emits its reasoning, its tool
arguments and its answer under the same key, that leaves no path which selects only the
answer — and a path chosen because it happens to fit the frames you have is a guess that
holds until the model returns one frame fewer.

Name the frames instead. Both halves are required; one alone matches everything or
nothing, and the loader refuses it.

```yaml
  response_format:
    answer_field: "$.content"
    answer_frame_field: "$.type"      # only frames where …
    answer_frame_value: "text_end"    # … this field equals this value
    stream: true
```

Frames that do not match are not consulted for the answer. If the value names no frame the
target sends, the answer comes back empty — and `generate` records an empty answer as a
transport failure rather than as an answer, so a mis-named frame costs a re-run and never a
page of findings about a system that did answer.

## Targets that answer asynchronously

Some products do not answer the request that asked the question. One call starts the work
and hands back a ticket; the answer is fetched from a second address once it is ready.
Configure both halves — `endpoints.receive` with a `GET` method makes the transport poll
rather than stream.

```yaml
  endpoints:
    chat:    { url: "https://…/analyzer", method: POST, body: { … } }
    receive: { url: "https://…/message/{{HANDLE}}", method: GET }

  response_format:
    handle_field: "$.aiMessage.id"   # the ticket, taken from the submit response
    ready_field:  "$.status"         # poll until …
    ready_value:  "saved"            # … this field equals this value
    answer_field: "$.text"
    poll_interval_seconds: 3
    poll_timeout_seconds: 300
```

`{{HANDLE}}` is the reason `handle_field` exists: a per-message identifier does not exist
until the submit returns, so the poll URL cannot be written in advance.

`ready_field` is not decoration. Without it, polling stops as soon as `answer_field`
matches anything — which is correct only for targets that create the answer field once
they have an answer to put in it. Against one that creates the record up front with
`text: ""`, that test is satisfied on the first poll and **every probe returns an empty
string**. Both halves are required and the loader refuses one alone.

Exhausting `poll_timeout_seconds` raises, and `generate` records the raise as a transport
error. An answer that never arrived is a failed measurement, not an empty one — returning
`""` would write a record that reads exactly like a system with nothing to say.
