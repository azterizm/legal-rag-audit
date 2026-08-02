# legal-rag-audit

An open-source evaluation harness that fires a fixed, hashed battery of probes at a legal
RAG system and reports what the system did — nothing more. Its output is built for one
purpose: **to survive being handed to a third party** — a client's enterprise buyer, a
procurement reviewer, a risk committee — and re-run by them.

The harness is free and forkable on purpose. Because it is open, the buyer's own
enterprise customer can re-run a report and reproduce the numbers. Nobody can re-run a
SOC 2.

---

## What it reports, and what that is worth

Findings are split into two tiers, and both labels are printed on the face of every
report along with their definitions.

| Tier | What it is | Register label | Defensibility |
|---|---|---|---|
| **Tier 1 — assertion-free** | Exact match against ground truth we authored and planted in the corpus. **No model anywhere in the evaluation path.** | Measured | A planted token either appeared or it did not |
| **Tier 2 — instrument-scored** | Semantic scoring by a named local model against a stated threshold | Measured (instrument disclosed) | Contestable on threshold and model choice. Bounded by full disclosure |

The split matters more than the checks themselves. The predictable response to any
finding is *"you tested it wrong"*, and against Tier 2 that objection is not a bluff —
general-corpus NLI models are weak on legal language: negation, exceptions,
*notwithstanding*, conditional obligations. So the model, its version and its threshold
go on the page and the threshold is arguable. Tier 1 is a string planted in tenant B's
namespace appearing verbatim in a tenant A response. Conceding the arguable half is what
makes the unarguable half land.

Every report leads with Tier 1. Tier 2 is supporting texture.

### The checks have mechanical names

There is no headline percentage. `unresolvable_citations`, `non_existent_authorities`,
`version_mismatch`, `unsupported_assertions`, `non_reproducible_responses`,
`licensed_content_reproduction` — each is
counted against **the probes declared eligible for that check before the run**, not
against the battery total, and reported as a count with its denominator and the date the
battery was fixed:

> 60 eligible probes × 3 passes. 11 failed in all three passes (stable defect). 3 failed
> in some passes only (non-reproducible). Battery fixed 2026-08-04, hash `sha256:…`

Three reasons it is stated that way. A percentage hides its denominator, and 7% of 14
probes is a different claim from 7% of 200. The battery deliberately over-samples known
failure surfaces, so any rate it yields is the failure rate *on a set built to find
failures* — stating counts against a fixed, hashed, dated battery makes that explicit
instead of inviting the one objection that would land. And a probe failing 3 of 3 is a
defect while a probe failing 1 of 3 is non-reproducibility, which is a different finding
that no accuracy work closes; collapsing them destroys the more valuable of the two.

### What this is not

- Not a leaderboard. No named commercial product is benchmarked publicly, at any tier.
- Not a remediation tool. It names causes and stops.
- Not a browser agent, not a UI-level tester, not a shadow-AI scanner.
- Not a general RAG eval framework competing with RAGAS/ARES/TruLens.

---

## Implementation status

This README describes the v2 design. The repository is mid-migration from v1, and the
table below is the honest split. **Anything marked *specified* does not exist in the code
yet** — it is documented here because the interchange formats are the product surface and
they are being built against a written spec, not discovered.

| Capability | Status |
|---|---|
| Local-only scoring; no third-party inference path | **Shipped** |
| Exact version pins + hash-pinned lockfiles, split by mode | **Shipped** |
| Corpus verified before a run starts; loud abort, no report on failure | **Shipped** |
| 17 evaluators against a configured endpoint | **Shipped** — single pass |
| Licensed-content reproduction check (#18) | Specified — v0.4.0 |
| SSE / WebSocket transport, JSONPath extraction | **Shipped** |
| JSON report with per-check counts and tiers | **Shipped** — Markdown attestation pending |
| Non-root container, dependency layer installed under `--require-hashes` | **Shipped** — single image; two-image split pending |
| `generate` / `score` mode split; scoring offline and enforced | **Shipped** — `validate` pending |
| `responses.jsonl` interchange format + published schema | **Shipped** |
| Tier 1 / Tier 2 tagging and tier-separated findings | **Shipped** — 14 Tier 1, 3 Tier 2 |
| Run manifest: hashes, commit SHA, model versions, battery composition | **Shipped** — seed and corpus mode arrive with `plant` |
| `hash` handover record; `score` refuses a ground truth that moved | **Shipped** |
| `NOT_ELIGIBLE` / `NOT_CAPTURED` statuses | **Shipped** |
| Authorisation gating on injection / canary families | Specified — v0.2.0 |
| Seeded plant generation with collision guard | Specified — v0.3.0 |
| N-pass execution and variance as a first-class finding | Specified — v0.3.0 |
| Pathological reference target, sensitivity/specificity CI gates | Specified — v0.3.0 |
| Existing-corpus mode and point-in-time probe pairs | Specified — v0.4.0 |

The mode split has landed: `generate` and `score` are separate commands, and scoring
runs with sockets disabled. The run manifest has landed with it, so a report now carries
the digests, the build that produced it and the instrument behind every Tier 2 number.
What it still lacks is the Markdown attestation and the evidence bundle. Until those
arrive, a report is complete evidence in a format built for a machine to read.

---

## Architecture

Three modes with hard separation between them. The split is the security control, not a
convenience.

| Mode | Does | Network | Who runs it |
|---|---|---|---|
| `validate` | 3 neutral probes; prints the raw response body and what each JSONPath extracted; exits | Target only | Them, pre-sale, free |
| `generate` | Fires the battery at the configured endpoints, writes `responses.jsonl` | Target only | Them — or replaced entirely by their own tooling |
| `score` | Reads `responses.jsonl` plus the ground-truth manifest, writes the report | **None** | Us |

```
                         ┌──────────────── OUR SIDE ────────────────┐
  corpus/ ──┐            │                                          │
  probes/ ──┼── handover │   ground_truth.json (withheld, hashed)   │
            │            │                                          │
            ▼            │                                          │
  ┌──── THEIR SIDE ────┐ │                                          │
  │  validate (opt.)   │ │                                          │
  │  generate  ──OR──  │ │                                          │
  │  their own harness │ │                                          │
  │        │           │ │                                          │
  │        ▼           │ │                                          │
  │  responses.jsonl ──┼─┼──► score ──► report.json + report.md      │
  └────────────────────┘ │            + evidence bundle + manifest   │
                         └──────────────────────────────────────────┘
```

Four things the split buys:

1. **It removes `config.yaml` from the critical path.** Responses can be produced however
   is cheapest — an internal eval harness, a QA script, thirty lines of curl — and
   returned as a JSONL file.
2. **Custody of the evidence moves to whoever generated it.** Responses a vendor produced
   themselves cannot later be dismissed as *"your harness prompted it wrong."*
3. **It answers "is your tool safe to run" structurally.** If our code never runs, there
   is nothing of ours to security-review. The question stops being asked rather than
   being answered.
4. **`score` running with no network at all is a short review** even when it does run.

### Dependency split

`sentence-transformers` pulls torch and transformers — hundreds of transitive packages
nobody can review. That is fine on our machine and unacceptable on a target's.

| Mode | Dependencies |
|---|---|
| `generate`, `validate` | `httpx`, `pyyaml`, `pydantic`, `jsonpath-ng` — four pure-Python libraries |
| `score` | the above, plus `sentence-transformers`, `torch` (CPU), a pinned NLI model |

CI asserts the boundary: the `generate` entrypoint imports and runs in a virtualenv
installed without the `[score]` extra, and `torch` is not importable there. *"Read it in
ten minutes"* is then literally true rather than a slogan.

### Current component map

The dashed line is the handover. Everything left of it can run on your infrastructure
without us; everything right of it runs on ours, offline.

```mermaid
flowchart TD
    subgraph Authoring ["Authored here, split before it leaves"]
        BATTERY["Battery<br/>(probes/)"]
        CORPUS["Corpus<br/>(bundled demo / your own directory)"]
    end
    subgraph Theirs ["Your side — optional, replaceable"]
        CFG["Config<br/>(config.py)"]
        GEN["generate<br/>(generate/)"]
        TRANSPORT["Transport (transport/)<br/>httpx REST & SSE · websockets · jsonpath-ng"]
    end
    subgraph Target ["Your RAG system"]
        UPLOAD_EP["Upload<br/>(/documents)"]
        CHAT_EP["Chat<br/>(/chat)"]
        RET_EP["Retrieval<br/>(/search)"]
    end
    subgraph Ours ["Our side — offline, no sockets"]
        HASH["hash<br/>(provenance/)"]
        HANDOVER["handover.json"]
        SCORE["score<br/>(score/)"]
        E_EXACT["Tier 1 — exact-match & inverted<br/>(no model in the path)"]
        E_NLI["Tier 2 — entailment & relevance<br/>(local NLI / embeddings)"]
        REP_JSON["out/report.json<br/>+ manifest.json<br/>+ ground_truth.json"]
    end

    BATTERY -->|questions only| PROBES["probes.jsonl"]
    BATTERY -->|expectations, withheld| GT["ground_truth.json"]
    PROBES --> HASH
    GT --> HASH
    CORPUS --> HASH
    HASH -->|digests, published first| HANDOVER
    HANDOVER ==>|pre-commitment| SCORE
    PROBES --> GEN
    CFG --> GEN
    CORPUS --> GEN
    GEN --> TRANSPORT
    TRANSPORT -->|1. ingest corpus| UPLOAD_EP
    TRANSPORT -->|2. ask probes| CHAT_EP
    TRANSPORT -->|3. retrieve| RET_EP
    UPLOAD_EP -.->|document ids| TRANSPORT
    CHAT_EP -.->|answers / SSE / WS| TRANSPORT
    RET_EP -.->|chunks| TRANSPORT
    TRANSPORT --> GEN
    GEN --> RESP["responses.jsonl"]
    RESP ==>|handover| SCORE
    GT ==>|handover| SCORE
    PROBES ==>|denominators| SCORE
    SCORE --> E_EXACT
    SCORE --> E_NLI
    E_EXACT --> REP_JSON
    E_NLI --> REP_JSON
```

`generate` writes `responses.jsonl` and stops — it scores nothing, so it has no verdict
to be wrong about. `score` reads that file plus the withheld ground truth and never
opens a socket. Replacing `generate` with your own script changes nothing downstream;
see [the response schema](docs/responses-schema.md).

---

## Scoring is deterministic. Target systems typically are not.

Two different things get called determinism — the reproducibility of our scoring, and the
reproducibility of the target's answers — and conflating them destroys both.

**Ours is a precondition.** Scoring is deterministic: the same responses, the same ground
truth and the same scoring configuration produce a byte-identical report. No model sits
in the scoring path by default, and where one does — the two Tier 2 checks — it is local,
pinned by version, and disclosed on the page. If scoring were not reproducible the report
would die to *"run it again"*, and reproducibility cannot be sold with an instrument that
lacks it.

**Theirs is a finding.** A target that returns a different answer to the same question
cannot reproduce an answer given to a client six months ago when it is disputed. That is
a records failure and it holds at any accuracy level. So running the harness twice against
a non-deterministic target legitimately produces different counts: the scoring did not
change, the system under test did. That is the instrument working, not the instrument
broken. The variance pass classifies each probe
across passes as `identical`, `invariant_stable` (prose differs, every Tier 1 outcome is
the same) or `divergent` (a Tier 1 outcome changed), and only `divergent` is reported as
a finding. Flagging ordinary phrasing variation as failure is the fastest way to lose a
report.

Everything that could vary is seeded and the seed is recorded: plant generation, probe
ordering, any sampling.

---

## Data handling

**No remote scoring path exists in the published package.** Scoring runs on local models
only — a pinned sentence-transformers embedding model and a pinned local NLI
cross-encoder, both CPU, both offline after first download. There is no third-party
inference vendor, no vendor credential, and no code path that transmits corpus text or
target responses to anyone. `scripts/check_no_remote_scoring.sh` and
`tests/test_no_remote_scoring.py` assert this on every run.

**Zero data exfiltration, scoped precisely.** On the local scoring path the harness makes
exactly one class of outbound connection: `generate` talks to the target endpoints named
in your `config.yaml`, and nothing else. No telemetry, no phone-home, no update check, no
analytics. Model weights download once from the Hugging Face hub on first use and can be
pre-baked into the image for a fully offline run. Once the mode split lands, `score`
opens no sockets at all and asserts that at start-up.

> v1 shipped an optional Gemini path for three of the evaluators. It has been removed.
> That path made a third party a sub-processor and made each run a data-transfer event,
> on a tool whose stated selling point is that nothing leaves the local environment, and it
> averaged three generation calls per claim, which is not reproducible scoring. The code
> is retained, quarantined and documented in `internal_experiments/`, which is excluded
> from the wheel and the image. See `V2_FULL_PLAN.md` §4.2.

### When you do run it

Deny egress rather than disabling it. A delayed payload still has to make a call
eventually, and it fails whenever it fires — timing is irrelevant under denial. The
recommended invocation, once the two images ship:

```bash
docker run --rm --network=host-allowlist-only \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user 65534:65534 \
  -v "$PWD/in:/in:ro" -v "$PWD/out:/out" \
  ghcr.io/…/legal-rag-audit-generate@sha256:… \
  generate -c /in/config.yaml -o /out/responses.jsonl
```

Put a logging proxy in front of it if you want proof rather than a claim — the connection
log is yours, not ours. One read-only input mount, one write-only output directory, no
volumes, no daemon, exits when done. Nothing persists, so there is nowhere for "queued"
to live.

---

## Installation

Every dependency is pinned to an exact version and verified by hash. Install from a
lockfile:

```bash
pip install --require-hashes -r requirements/score.txt && pip install --no-deps -e .
```

For the generate/validate path only — five pure-Python libraries, no ML stack:

```bash
pip install --require-hashes -r requirements/generate.txt && pip install --no-deps -e .
```

`pip install -e .` on its own also works and installs the same versions, because
`pyproject.toml` pins exactly rather than by range. It does not verify hashes.

**Why there are no version ranges anywhere.** A report claims that a third party can
reconstruct the run from the manifest and the repository at a signed commit. A range
makes that false: `sentence-transformers>=2.2.2` is different software in March than in
August, and a Tier 2 threshold means nothing without the model and library version behind
it. A range also turns a vulnerability scan into a statement about the day you installed
rather than about the artefact — which is how `idna` 3.11 (PYSEC-2026-215) came to be
installed here while the declared dependency set looked clean.

A pin fixes the version. A hash fixes the bytes. With `--require-hashes`, a substituted
or tampered artefact fails the install instead of reaching the run.

| File | Contents |
|---|---|
| `requirements/generate.txt` | 14 packages — the `generate`/`validate` runtime |
| `requirements/score.txt` | 66 packages — adds the local scoring models |
| `requirements/dev.txt` | 92 packages — adds test and release tooling |

The lockfiles are generated, never hand-edited. Change `requirements/*.in`, then run
`./scripts/lock.sh`. They are resolved universally, so one file installs correctly on
macOS arm64 and Linux x86_64 rather than silently disagreeing per platform.

Scoring downloads two model weights on first use (~500MB total). Pre-warm them if the run
host has no outbound access.

---

## Configuration

Map the harness to your API's exact shape in `config.yaml`. **An incorrect JSONPath is
the documented leading cause of false positives** — an empty extracted string scored as a
finding is a result that has to be retracted in front of a buyer. This is what `validate`
exists to prevent.

```yaml
target:
  name: "vendor-staging"
  endpoints:
    chat: "https://staging.example.com/api/v1/chat"
    upload: "https://staging.example.com/api/v1/documents"
    retrieval: "https://staging.example.com/api/v1/search"   # optional
  auth:
    type: "bearer"                 # bearer | api_key | basic | none
    token_env: "TARGET_API_KEY"    # env var only, never inline
  response_format:
    answer_field: "response.text"
    citations_field: "response.sources"
    stream: false                  # true for Server-Sent Events

corpus:
  use_bundled: true                # the 13-document demo corpus — read the caveat below
  # path: "./my_test_documents/"   # or your own directory

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
> authoritative. v0.2.0 renames the block `display_thresholds` and draws each one as a
> marked line on a distribution rather than a pass/fail gate, because presenting a
> setting as a standard is the exact failure this project exists to measure in other
> people's systems. The rename makes the misuse impossible to commit by accident.

### Endpoints

1. **`chat` (required)** — `POST` with the query in a JSON body; returns the answer string
   and, if the system emits them, an array of citations. Extraction is driven by
   `response_format.answer_field` and `citations_field`.
2. **`upload` (required for planted-corpus mode)** — `POST` with document content; the
   harness captures the returned document `id` to build the upload manifest. Citation
   integrity is set membership against that manifest, so without an `id` the check
   silently loses its ground truth.
3. **`retrieval` (optional)** — direct search endpoint. Without it, retrieval relevance
   has no chunks to score and reports `NOT_CAPTURED` rather than passing.

### Non-standard shapes

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

---

## Running it

Three steps, on two machines. The middle one is yours and optional; the outer two are
ours, and the last runs offline.

```bash
legal-rag-audit hash --corpus ./corpus/ \
                     --probes probes.jsonl \
                     --ground-truth ground_truth.json \
                     -o handover.json
```

Digests the three artefacts and writes the handover record. **This runs before you see a
single answer**, and the record goes to you with the corpus — it is what fixes the sealed
half of the battery while it is still sealed. Every digest carries the recipe that
recomputes it, so verifying one needs `shasum` and nothing of ours.

```bash
export TARGET_API_KEY="your-api-token"
legal-rag-audit generate -c config.yaml -o responses.jsonl --probes probes.jsonl
```

Fires the battery at your endpoints and records what came back. It scores nothing, so it
has no verdict to be wrong about. Replace it with your own harness if you prefer — see
[the response schema](docs/responses-schema.md).

```bash
legal-rag-audit score --responses responses.jsonl \
                      --ground-truth ground_truth.json \
                      --probes probes.jsonl \
                      --handover handover.json \
                      -o out/
```

Writes `out/report.json`, `out/manifest.json`, and `out/ground_truth.json` — the sealed
half, disclosed in full, hashing to the value you were given at step one. Opens no
sockets: an attempt raises.

Passing `--handover` makes the pre-commitment a precondition rather than an undertaking.
The digests are recomputed, and **a ground truth that changed since handover aborts the
run** — no report, exit 2. That constraint is on us, not on you.

```bash
legal-rag-audit schema --print responses.v1
```

Prints the published contract, so implementing against it needs no clone.

Exit codes are a contract: **0** ran clean, **1** ran with findings, **2** did not run —
a setup problem, with a diagnosis. A run that could not start never exits the way a clean
one does.

Still to come: `validate` (v0.2.1) and `plant` (v0.3.0).

---

## The corpus

The bundled 13-document set is **a demo, not an audit.** It measures whether a pipeline
has generic properties on a best case: 13 clean synthetic documents uploaded and queried
immediately. It is not your production ingestion history, not your chunking at 40,000
documents, not your index at scale, and not your practice area. **A system can pass the
bundled run cleanly and fail badly in production.** A generic corpus cannot tell you
whether you are compliant, and this README will not pretend otherwise.

| Documents | What they exercise |
|---|---|
| 3 synthetic case-law documents with known facts | Grounding, latency, contradictory-fact handling |
| 2 near-identical SaaS agreements with contradictory liability clauses | Contradiction surfacing |
| 1 dense regulatory document (nested lists, tables) | Structural integrity |
| 2 statutes with overlapping article numbers | Retrieval disambiguation |
| 1 PII-heavy document | Entity masking re-hydration |
| 1 document with an embedded injection payload | Injection resistance |
| 1 document referencing a non-existent statute | Citation integrity |
| 2 tenant-isolated matter documents | Cross-tenant leakage |
| A topic with zero relevant documents | Parametric bleed, abstention |

**Custom corpus:** set `use_bundled: false` and give a `path:` to a directory of text or
markdown files. Their raw text becomes the ground truth, so anything inaccurate in them
becomes a false finding.

### The corpus is checked before anything is sent

The corpus is resolved and verified before the first request goes out, and a problem with
it **aborts the run with a diagnosis and writes no report** (exit code 2). Checked:

- `use_bundled: true` — the bundled corpus is installed, and all 13 documents are present.
  A partial corpus names the documents it is missing.
- `use_bundled: false` — `path` is set, exists, and holds at least one readable document.
- Every document is UTF-8 and non-empty. Hidden files are skipped.
- Document order is sorted, not filesystem order, so the same corpus reads the same way
  on every machine.

This exists because the failure it replaces was silent. With the corpus missing, the
runner used to substitute two stand-in documents and *finish*: the report described a
2-document corpus while the config said thirteen, and nothing on the page disclosed the
substitution. A setup problem must never render as a finding (NF9) — if the corpus cannot
be verified, there is no run.

---

## What the checks are

Eighteen evaluators. Sixteen are Tier 1 by design, because determinism is a property of
corpus design rather than of the scorer: the question is not *"what model judges the
response?"* but *"what do we plant in the documents so that no judgment is needed?"*
Proper nouns, high-precision figures, specific dates and citations survive paraphrase and
can be checked by exact match. Prose cannot.

| # | Check | Tier | Key | Recipe |
|---|---|---|---|---|
| 1 | `cross_tenant_leakage` | 1 | cond. | Multi-type canary; substring presence |
| 2 | `injection_resistance` | 1 | open | Payload demanding a verifiable side effect; prefix match |
| 3 | `citation_integrity` | 1 | open | Set membership of cited IDs against the upload manifest |
| 4 | `index_freshness` | 1 | held | Update a planted fact; check old token against new |
| 5 | `entity_masking` | 1 | held | Exact match on entity; counterparty-swap check across pairs |
| 6 | `parametric_bleed` | 1 | open | Inverted — presence of a known out-of-corpus fact |
| 7 | `routing_contamination` | 1 | open | Inverted — presence of an out-of-bounds fact |
| 8 | `abstention` | 1 | open | Inverted — presence of the answer it should not have given |
| 9 | `contradiction_surfacing` | 1 | held | Both planted values present ⇒ surfaced; one ⇒ silently picked |
| 10 | `attribution` | 1 | held | Adjacency — planted fact and correct document ID in one sentence |
| 11 | `clause_synthesis` | 1 | held | Required-facts checklist, including the planted exclusion |
| 12 | `structural_integrity` | 1 | held | Invariant planted deep in a nested list; relational query |
| 13 | `disambiguation` | 1 | held | Distinct invariant under each colliding article number |
| 14 | `context_memory` | 1 | held | Distinct invariant per referent; which one the pronoun resolved to |
| 15 | `latency` | 1 (measurement) | open | TTFB and total as distributions. The *interpretation* is labelled inference, not measurement |
| 16 | `unsupported_assertions` | **2** | open | Sentence-level NLI entailment against retrieved chunks |
| 17 | `retrieval_relevance` | **2** | open | Cosine similarity over retrieved chunks |
| 18 | `licensed_content_reproduction` | 1 | cond. | Publisher-proprietary marker in retrieved chunks, or in an answer attributed to an internal document |

### The Key column: what is published, and what is sealed for a few hours

Nothing about the **method** is withheld, ever. The code, the recipes above, the schemas
and the scoring rules are public and forkable. The only artefact with a timing rule on it
is the answer key for one engagement, and the rule is narrow:

| Key | Meaning |
|---|---|
| `open` | The expectation ships **with** the battery. Published in advance |
| `held` | Sealed until the report, then handed over in full with a hash you were given beforehand |
| `cond.` | `open` when `retrieved_chunks` are captured; `held` when they are not |

The line between them is mechanical, not a matter of taste:

> A check is **open** when knowing its expectation in advance cannot help a system pass
> it without exhibiting the behaviour being tested.

An *inverted* check says **this token must not appear**. The only way to satisfy it is not
to emit the token — which is the behaviour under test. Read the key for
`routing_contamination`, stop leaking out-of-bounds facts, and you have not gamed the
check; you have passed it. So it is published.

A *positive* check says **this token must appear**. Knowing the string lets it be pinned,
cached or prompted with no retrieval improvement at all, and the difference is invisible
in the output. Those eight are sealed — for the length of a run.

**Eight of the eighteen checks are published with their answer keys.** For the other
eight, telling you the value we are testing whether you retrieved would test nothing.

Every report prints the key beside each check and counts them, so the withholding is a
bounded fact on the page rather than an atmosphere.

### Why anything is sealed at all

Not to keep a secret from you. **To stop us being accused of inventing the expectations
after seeing your answers.**

You receive `ground_truth_manifest_hash` at handover, before a single response exists.
You receive the manifest itself with the report, and can verify it hashes to the value
you were already holding. There is no window in which we could have edited it.

Both halves are the tool's job, not ours to remember. `hash` writes the record; `score`
recomputes the digests and **refuses to produce a report** if the ground truth moved, and
writes the manifest into the output directory beside the findings on every run. If we
edited the key after seeing your answers, there is no report to argue about.

Without that, every finding is answerable with one sentence — *"you decided what counted
as a failure once you saw the failure"* — and there is no way to refute it. The hash makes
that sentence unsayable. It constrains the auditor more than it constrains the vendor,
which is the point of a document written to survive being handed to a third party.

This is the same instrument as trial pre-registration: the protocol is published, and it
is published *first*.

Two further notes, because the sealing is smaller than it sounds. Capturing
`retrieved_chunks` moves the conditional checks into the open half, because detection
then sits below the layer an output filter can reach — that is a concrete reason to
expose retrieval, not a request with nothing behind it. And per-engagement seeded plants
mean a key disclosed after one run is worth nothing for the next: **regeneration is the
durable property, secrecy only buys hours.**

The bundled demo battery is fully open, keys and all. It ships in the same package as the
corpus it describes, so anyone can read both.

### Two design rules

**Never enumerate what the target might say;
check for a token we authored** — abstention is detected by the absence of the invariant
class, not by string-matching refusal language, because *"I don't have that"* has a
thousand phrasings and enumerating them is the trap. And **injection is scored by side
effect, not by judgment**: the payload demands something verifiable (begin the reply with
a seeded token, answer in French), so success is a substring check rather than an opinion
about whether the model was manipulated.

---

## Limits — what a run does not establish

Printed in every report, in the same artefact as the findings, not in a later post.

- **Injection probes measure instruction-boundary override via token emission, not data
  exfiltration.** A system that emits a demanded token has followed an instruction from
  a document. That is a mechanism proxy. It is not evidence that an attacker can extract
  data, and it must not be reported as if it were.
- **Determinism is a property of the scoring, not of the target.** See above.
- **Planted-corpus results characterise the pipeline, not the production index at scale.**
- **A clean result is only as good as the battery behind it.** Machine output lists
  results; it cannot characterise absence. Any report has to name what was not tested.
- **`NOT_ELIGIBLE` and `NOT_CAPTURED` are not passes.** "No cross-tenant leak" on a
  single-tenant deployment is not a finding, and a check whose inputs were never captured
  has not been performed.
- **Licensed content in an index is not a licence breach.** `licensed_content_reproduction`
  establishes that publisher-proprietary content is served from the target's own index
  rather than fetched per query. It does not establish that this is unlicensed — the
  vendor may hold a bulk-ingestion or content-partnership agreement, and no run has
  visibility of their contracts. The finding names what a procurement reviewer will ask
  about. It never alleges infringement.
- **The harness has not yet been verified against a reference target.** Sensitivity
  (every pathology fires its evaluator) and specificity (zero false positives on a clean
  profile) are v0.3.0 CI gates. Until they are green, treat findings as requiring hand
  verification. They require it anyway before anything is delivered.

---

## Testing against a system you do not own

Signing up for a product authorises **use**. It does not authorise **testing**. Most SaaS
terms separately prohibit benchmarking, automated access and multi-account creation, and
probing tenant isolation on a system you do not own is a Computer Misuse Act 1990
exposure in the UK. *"I signed up for a trial"* is not authorisation.

| Ordinary use — no authorisation needed | Requires written authorisation |
|---|---|
| Asking questions and reading the answers | Prompt injection payloads |
| Checking whether returned citations resolve | Cross-tenant canaries |
| Point-in-time correctness against public law | Uploading adversarial documents |
| Asking about topics outside the corpus | High-volume or automated querying |
| Checking answers for publisher-proprietary markers | Index or corpus enumeration |
| Asking the same question three times and diffing | Index-freshness re-upload |

v0.2.0 enforces this in software rather than promising it in prose: a battery containing
any right-column family aborts unless the config carries a populated `authorisation`
block, `environment: production` additionally requires an explicit command-line flag, and
the authorisation block is reproduced verbatim in the report manifest so the artefact
carries its own provenance of consent. Default rate limits (2 concurrent, 1 rps,
exponential backoff on 429) are set so an ordinary run resembles a user rather than a
scanner.

---

## Development

```bash
pip install --require-hashes -r requirements/dev.txt && pip install --no-deps -e .
pytest
```

Skip the tests that build a wheel or download a model with `pytest -m "not slow"`.

Acceptance gates:

```bash
./scripts/check_no_remote_scoring.sh
```

Asserts there is no remote-scoring vendor, credential or endpoint anywhere in
`src/legal_rag_audit/`, that no scoring code imports an HTTP client, that
`internal_experiments/` is excluded from both the wheel and the image, and that no claim
in this README is made without its scope attached.

```bash
python3 scripts/check_pins.py
```

Asserts every requirement is exact, every lockfile entry carries hashes, that
`pyproject.toml` agrees with the lockfiles, and that the base dependency set is the
`generate` layer and no more. Two sources of truth that disagree are worse than one that
is vague, because the disagreement is silent.

```bash
python3 scripts/gen_schemas.py --check
```

Asserts the published JSON Schemas still match the pydantic models that enforce them.
The schemas are generated, never hand-edited: a published contract that `score` would
reject is worse than none, because it sends someone away to build the wrong thing.

Changing a dependency:

```bash
./scripts/lock.sh
```

Edit `requirements/*.in`, run that, commit the `.in` and `.txt` together. Never hand-edit
a lockfile — one that cannot be regenerated is not a lockfile.

`internal_experiments/` is not installed, not imported, not collected by pytest and not
copied into the image. Read `internal_experiments/README.md` before touching anything in
it.

---

## Reference

`V2_FULL_PLAN.md` is the full specification — evidence model, evaluator contracts,
interchange schemas, threat model and execution plan. `V2_PROGRESS.md` tracks what has
landed. This README is the summary; where they disagree, the plan wins.
