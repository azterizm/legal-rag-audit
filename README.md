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
| Exact version pins + hash-pinned lockfiles, split by mode | **Shipped** — four layers, cross-checked for agreement |
| CycloneDX SBOM per dependency layer | **Shipped** — generated from the lockfiles, drift-gated |
| Public CI: tests, gates, `pip-audit` / Bandit / Semgrep / Trivy | **Shipped** — actions pinned by commit SHA |
| Signed releases: GPG tag, SLSA provenance, cosign | **Shipped** — `scripts/verify_release.sh` is the reader's half |
| Corpus verified before a run starts; loud abort, no report on failure | **Shipped** |
| 17 evaluators against a configured endpoint | **Shipped** — single pass, all rewritten to the §8.2 recipes |
| Licensed-content reproduction check (#18) | Specified — v0.4.0 |
| SSE / WebSocket transport, JSONPath extraction | **Shipped** |
| JSON report with per-check counts and tiers | **Shipped** — published contract, `report.v2` |
| Markdown attestation, evidence bundle, Tier 2 distributions | **Shipped** |
| Non-root container, base image pinned by digest, deps under `--require-hashes` | **Shipped** — single image; the split, publication and image signing are pending |
| `generate` / `score` mode split; scoring offline and enforced | **Shipped** — `validate` pending |
| `responses.jsonl` interchange format + published schema | **Shipped** |
| Tier 1 / Tier 2 tagging and tier-separated findings | **Shipped** — 15 Tier 1, 2 Tier 2 |
| Run manifest: hashes, commit SHA, model versions, seed, corpus mode, battery composition | **Shipped** |
| `hash` handover record; `score` refuses a ground truth that moved | **Shipped** |
| `NOT_ELIGIBLE` / `NOT_CAPTURED` statuses | **Shipped** |
| Authorisation gating on injection / canary families | Specified — v0.2.0 |
| Seeded plant generation with collision guard | **Shipped** — `plant`, 29 invariants across 15 documents |
| Two-phase corpus upload for index freshness | **Shipped** |
| N-pass execution and variance as a first-class finding | **Shipped** — `response_divergence`, Tier 1 |
| Pathological reference target, sensitivity/specificity CI gates | Specified — v0.3.0 |
| Existing-corpus mode and point-in-time probe pairs | Specified — v0.4.0 |

The mode split has landed: `generate` and `score` are separate commands, and scoring
runs with sockets disabled. A run now produces a complete handover document — the
provenance manifest, the findings, verbatim excerpts for every Tier 1 instance, the
distribution behind every Tier 2 number, and the ground truth disclosed in full.

Every expectation a Tier 1 check scores against is now a **plant**: a value minted from
the run seed, guarded against collision with the corpus and with every other plant, and
inserted at a declared location. A key disclosed after one run is worthless for the next,
because the next run regenerates. That also took the last model out of Tier 1 — abstention
is scored by the presence of a specific claim rather than the entailment of a refusal, so
it needs no cross-encoder and no threshold.

Two sections of the attestation are deliberately left for a person to write: the
representation delta needs their published claims quoted with a URL and a date, and the
mechanism section needs an architectural reading this diagnostic cannot make. Generating
either would be the failure the tool exists to measure in other people's systems.

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
        SEED["Run seed"]
        PLANT["plant<br/>(plants/)<br/>HMAC mint · collision guard"]
        BATTERY["Battery<br/>(probes/)"]
        CORPUS["Corpus<br/>base/ + revision/"]
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
        REP_JSON["out/<br/>report.json · report.md<br/>manifest.json · ground_truth.json<br/>evidence/"]
    end

    SEED --> PLANT
    PLANT -->|invariants inserted at declared locations| CORPUS
    PLANT -->|minted values| BATTERY
    BATTERY -->|questions only| PROBES["probes.jsonl"]
    BATTERY -->|expectations + plants, withheld| GT["ground_truth.json"]
    PROBES --> HASH
    GT --> HASH
    CORPUS --> HASH
    HASH -->|digests, published first| HANDOVER
    HANDOVER ==>|pre-commitment| SCORE
    PROBES --> GEN
    CFG --> GEN
    CORPUS --> GEN
    GEN --> TRANSPORT
    TRANSPORT -->|1. ingest base corpus| UPLOAD_EP
    TRANSPORT -->|2. ask probes| CHAT_EP
    TRANSPORT -->|3. retrieve| RET_EP
    TRANSPORT -->|4. upload revision, wait, re-ask| UPLOAD_EP
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

Divergence is decided on **Tier 1 outcomes only**. A Tier 2 similarity of 0.851 on one
pass and 0.849 on the next crosses a threshold this scorer was configured with, not one
the target agreed to; counting that as their instability would report a setting of ours
as a property of their system.

Ask each probe three times:

```bash
legal-rag-audit generate -c config.yaml -o responses.jsonl --passes 3
```

One pass is the default rather than three, because tripling the request count against
someone else's endpoint is their decision and not one a default should take for them. At
one pass the report says nothing was compared instead of reporting stability.

**With N passes every count splits in two.** 15 eligible probes × 3 passes is 45
observations, and the report never collapses them: a defect that reproduced on every pass
and one that appeared on a single pass are different findings about different problems.
The second is usually the more valuable, because it is the one a vendor cannot reproduce
on their own.

Everything that could vary on our side is seeded and the seed is recorded: plant
generation, probe ordering, any sampling.

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
pre-baked into the image for a fully offline run. `score` opens no sockets at all and
asserts that at start-up — CI runs the whole `plant → hash → score` route inside an empty
network namespace, where a socket call fails rather than resolving.

> v1 shipped an optional Gemini path for three of the evaluators. It has been removed.
> That path made a third party a sub-processor and made each run a data-transfer event,
> on a tool whose stated selling point is that nothing leaves the local environment, and it
> averaged three generation calls per claim, which is not reproducible scoring. The code
> is retained, quarantined and documented in `internal_experiments/`, which is excluded
> from the wheel and the image. See `V2_FULL_PLAN.md` §4.2.

### When you do run it

Deny egress rather than disabling it. A delayed payload still has to make a call
eventually, and it fails whenever it fires — timing is irrelevant under denial.

The shipped `Dockerfile` runs as UID 65532 and installs from the hash-pinned lockfile on
a base image pinned by digest. What it is **not** yet: split into a small `generate`
image and a `score` image, published, or signed. So the invocation below is the target,
not something you can run today — building it yourself from this repository is the
current path, and the artefact route below is the better one.

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
| `requirements/audit.txt` | 100 packages — the security scanners, installed by CI only |

The scanners are a fourth layer rather than four more lines in `dev.txt`, for the same
reason `generate` and `score` are split: the set a person installs should be the set they
need. Semgrep alone pulls several dozen transitive packages, and burying them in the file
a contributor runs `pip install -r` against would undo the property that makes reading the
dependency list feasible.

The lockfiles are generated, never hand-edited. Change `requirements/*.in`, then run
`./scripts/lock.sh`. They are resolved universally, so one file installs correctly on
macOS arm64 and Linux x86_64 rather than silently disagreeing per platform.

Scoring downloads two model weights on first use (~500MB total). Pre-warm them if the run
host has no outbound access.

---

## Supply chain and provenance

The full position, with the command next to every claim, is in
[`SECURITY.md`](SECURITY.md). The short version:

| Question | Answer | Check it yourself |
|---|---|---|
| What is in it? | CycloneDX 1.6 SBOM per layer, in [`sbom/`](sbom/) | `python3 scripts/gen_sbom.py --check` |
| Are the bytes fixed? | Every entry `==` and hashed | `python3 scripts/check_pins.py` |
| Is it scanned? | `pip-audit`, Bandit, Semgrep, Trivy — weekly and on push | [the runs](https://github.com/azterizm/legal-audit-rag/actions/workflows/security.yml) |
| Who published this release? | GPG-signed tag, verified before the build starts | `./scripts/verify_release.sh <tag>` |
| Was it built from that commit? | SLSA provenance from a public workflow | same script |
| Is this the same file? | Cosign signature in the public Rekor log | same script |

Two decisions worth stating rather than leaving to be discovered.

**The SBOMs are generated from the lockfiles, not from an installed environment.** An
environment SBOM describes whatever happened to be on the machine that ran the scanner;
the lockfile is what the repository commits to, and its hashes are the same bytes
`--require-hashes` enforces at install time. They also carry the real resolution graph, so
you can see that torch arrives through `sentence-transformers` rather than because we
asked for it. One per layer, because a merged document listing torch would misdescribe
what a target installs — the only question they are asking.

**Every CI action is pinned to a commit SHA, never a tag.** A tag is a mutable pointer:
`actions/checkout@v7` runs whatever its owner moves that tag to. Pinning the whole
dependency tree to its bytes and then trusting six mutable references in CI would leave
the claim resting on the weakest link in it. Same for the Dockerfile's base image.
`tests/test_supply_chain.py` fails the build if an unpinned reference appears.

**Link the runs, not a badge.** A badge asserts a state. A link shows the command, the
version, the output and the date, and lets you re-run the whole thing on a fork — the
free version of a third-party audit, and unlike a paid one it does not go stale.

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
  mode: "planted"                  # plant a seeded corpus (default) | existing
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

Four steps, on two machines. The third is yours and optional; the rest are ours, and the
last runs offline.

```bash
legal-rag-audit plant --seed "$RUN_SEED" -o run/
```

Mints one invariant per declared slot, guards each against collision with the corpus and
with every other plant, and writes the corpus, the probe file and the answer key. Every
value is `HMAC-SHA256(seed, "<plant_id>#<attempt>")` formatted per type, so a third party
holding the seed regenerates the identical battery and can check that the corpus they were
sent is the corpus we said we planted. Omit `--seed` and it uses the published demo seed —
reproducible by anyone, which is right for a demonstration and stated on the report.

The corpus lands in two states: `run/corpus/base/` is uploaded first, `run/corpus/revision/`
replaces its counterpart later. That is what makes index freshness measurable at all —
*not yet indexed* and *never invalidated* are different findings and only the elapsed time
between the two phases separates them.

```bash
legal-rag-audit hash --corpus run/corpus \
                     --probes run/probes.jsonl \
                     --ground-truth run/ground_truth.json \
                     -o run/handover.json
```

Digests the three artefacts and writes the handover record. **This runs before you see a
single answer**, and the record goes to you with the corpus — it is what fixes the sealed
half of the battery while it is still sealed. Every digest carries the recipe that
recomputes it, so verifying one needs `shasum` and nothing of ours.

```bash
export TARGET_API_KEY="your-api-token"
legal-rag-audit generate -c config.yaml \
                         --corpus run/corpus \
                         --probes-in run/probes.jsonl \
                         -o responses.jsonl
```

Fires the battery at your endpoints and records what came back. It scores nothing, so it
has no verdict to be wrong about. Replace it with your own harness if you prefer — see
[the response schema](docs/responses-schema.md).

```bash
legal-rag-audit score --responses responses.jsonl \
                      --ground-truth run/ground_truth.json \
                      --probes run/probes.jsonl \
                      --handover run/handover.json \
                      -o out/
```

Writes:

| File | What it is |
|---|---|
| `report.json` | The evidence. A published contract — `legal-rag-audit schema --print report.v2` |
| `report.md` | The testimony. Provenance, findings, limits, in that order |
| `manifest.json` | Digests, build, instruments — also embedded in `report.json` |
| `ground_truth.json` | The sealed half, disclosed in full, hashing to the value you were given at step one |
| `evidence/` | One file per Tier 1 finding: the excerpt, the token, the probe, the pass |

Opens no sockets: an attempt raises.

Passing `--handover` makes the pre-commitment a precondition rather than an undertaking.
The digests are recomputed, and **a ground truth that changed since handover aborts the
run** — no report, exit 2. That constraint is on us, not on you.

```bash
legal-rag-audit schema --print responses.v2
```

Prints the published contract, so implementing against it needs no clone.

Exit codes are a contract: **0** ran clean, **1** ran with findings, **2** did not run —
a setup problem, with a diagnosis. A run that could not start never exits the way a clean
one does.

Still to come: `validate` (v0.2.1).

### If you would rather we never touched your endpoint

Skip step three. Keep the endpoint entirely — no config of ours, no credentials shared,
nothing of ours executed against your infrastructure. Ingest the planted corpus with
whatever you already use, put the questions in `run/probes.jsonl` through your own eval
harness or QA script, and return a `responses.jsonl`. `score` cannot tell the difference,
and neither can the report.

```bash
legal-rag-audit score --responses your-harness-output.jsonl \
                      --ground-truth run/ground_truth.json \
                      --probes run/probes.jsonl \
                      --handover run/handover.json \
                      -o out/
```

`plant`, `hash` and `score` import nothing from the transport layer, and a test runs this
whole route in an environment with `httpx` uninstalled — so *"no endpoint access"* is a
property of the build rather than a promise on a page.

**Two things it costs, and neither weakens a finding.** What you can capture is yours to
declare: a harness that does not surface `retrieved_chunks` disables the two Tier 2 checks,
one that returns no `document_ids` disables citation integrity, and all of it shows on the
page as `NOT_CAPTURED` rather than as a pass. And index freshness needs you to apply the
revision and record the wait; if you cannot, leave the `after_revision` probes unasked —
asking them against an unchanged corpus and reading the unchanged answer as a stale index
would be a finding manufactured out of your constraints.

**One thing it strengthens.** Responses your harness produced cannot later be dismissed
with *"your tool prompted it wrong."* Custody of the evidence is yours, and that runs in
your favour and ours at the same time.

`score` checks every record's `query` against the probe text that was hashed at handover,
because on this route nobody watched the questions go out. Identical is counted and
printed. Wrapped in a system preamble is ordinary — the finding stands, and the report
names those probes rather than claiming they were put verbatim. A query that does not
contain its probe's text at all aborts the run: that record answers a different question,
and scoring it would produce a finding about something nobody asked.

What no software can establish is that what reached the file is what your system returned.
The report says so in its limits rather than implying otherwise.

---

## The corpus

`plant` writes a 15-document corpus from 14 templates, with 29 invariants inserted at
declared locations. It is **a demo, not an audit.** It measures whether a pipeline has
generic properties on a best case: fifteen short synthetic documents uploaded and queried
immediately. It is not your production ingestion history, not your chunking at 40,000
documents, not your index at scale, and not your practice area. **A system can pass this
run cleanly and fail badly in production.** A generic corpus cannot tell you whether you
are compliant, and this README will not pretend otherwise.

| Documents | What they exercise |
|---|---|
| 2 tenant-isolated matter files, 3 invariant types in one | Cross-tenant leakage |
| 2 documents carrying a side-effect payload | Injection resistance |
| 2 near-identical supplier agreements with contradictory caps | Contradiction surfacing, latency |
| 1 nested service schedule with a leaf four levels under its heading | Structural integrity |
| 2 statutes with overlapping article numbers | Retrieval disambiguation, attribution |
| 1 settlement schedule with paired counterparties | Entity masking re-hydration |
| 1 namespace-scoped note | Routing contamination |
| 1 digest of authorities | Citation integrity |
| 1 chronology with three distinct referents | Context memory |
| 1 retainer notice, in two states | Index freshness |
| A question the corpus deliberately cannot answer | Parametric bleed, abstention |

Each document carrying a positive expectation gets **at least three invariant types,
including one entity and one figure**. A system that paraphrases a leaked clause still
emits the counterparty name or the amount, because those are the payload. A single planted
string would be defeated by rewording.

**What the collision guard checks**, and what it does not, goes into every ground-truth
manifest. It verifies that no value occurs in the corpus as authored, that no two plants
contain one another, that coined words are not in a bundled register of real parties, and
that every generated neutral citation carries a number above the range any division of the
High Court has issued in a year. It does **not** check the body of reported authority:
scoring is offline by construction, so no lookup leaves the machine, and the residue is
closed by manual review of the generated citations in the first corpus of each domain.

**Existing corpus:** set `mode: existing` and give a `path:`. Nothing is uploaded and
ground truth is external — point-in-time pairs and licensed-content reproduction land
there in v0.4.0.

### The corpus is checked before anything is sent

The corpus is resolved and verified before the first request goes out, and a problem with
it **aborts the run with a diagnosis and writes no report** (exit code 2). Checked:

- A planted root has a `base/` directory. A flat directory is refused rather than read as
  one, because reading it that way would silently drop the revision phase and take index
  freshness with it.
- `mode: existing` — `path` is set, exists, and holds at least one readable document.
- Every document is UTF-8 and non-empty. Hidden files are skipped.
- Document order is sorted, not filesystem order, so the same corpus reads the same way
  on every machine.
- Every template slot is filled and every declared plant is inserted. A plant in the
  answer key and not in the corpus would fail a correct system.

This exists because the failure it replaces was silent. With the corpus missing, the
runner used to substitute two stand-in documents and *finish*: the report described a
2-document corpus while the config said more, and nothing on the page disclosed the
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
| 1 | `cross_tenant_leakage` | 1 | cond. | Multi-type canary; substring presence in answer **and retrieved chunks** |
| 2 | `injection_resistance` | 1 | open | Payload demanding a verifiable side effect; prefix or suffix match |
| 3 | `citation_integrity` | 1 | open | Set membership of cited IDs against the upload manifest. Two of three counters scored — see below |
| 4 | `index_freshness` | 1 | held | Revise a planted fact; superseded value against current, with the wait recorded |
| 5 | `entity_masking` | 1 | held | Exact match on entity; counterparty swap and mask-token leak split out |
| 6 | `parametric_bleed` | 1 | open | Inverted — presence of a known out-of-corpus fact |
| 7 | `routing_contamination` | 1 | open | Inverted — presence of an out-of-bounds fact |
| 8 | `abstention` | 1 | open | Inverted — presence of a specific claim of the shape the question asked for |
| 9 | `contradiction_surfacing` | 1 | held | Both planted values ⇒ surfaced; one ⇒ silently picked; neither ⇒ not captured |
| 10 | `attribution` | 1 | held | Adjacency — planted fact and correct document ID in one sentence |
| 11 | `clause_synthesis` | 1 | held | Required-facts checklist, including the planted exclusion |
| 12 | `structural_integrity` | 1 | held | Invariant planted deep in a nested list; relational query |
| 13 | `disambiguation` | 1 | held | Distinct invariant under each colliding article number |
| 14 | `context_memory` | 1 | held | Distinct invariant per referent; which one the pronoun resolved to |
| 15 | `latency` | 1 (measurement) | open | TTFB and total as distributions. The *interpretation* is labelled inference, not measurement |
| 16 | `unsupported_assertions` | **2** | open | Sentence-level NLI entailment against retrieved chunks |
| 17 | `retrieval_relevance` | **2** | open | Cosine similarity over retrieved chunks |
| 18 | `licensed_content_reproduction` | 1 | cond. | Publisher-proprietary marker in retrieved chunks, or in an answer attributed to an internal document |

**Fifteen of the eighteen are shipped and Tier 1**; #18 arrives with existing-corpus mode
to make sixteen. A test reads every Tier 1 evaluator's imports and fails the build if a
model is reachable from one, so *"no model anywhere in the evaluation path"* is asserted
rather than promised.

Plus one that is **not an evaluator** and is counted apart from the eighteen:

| Check | Tier | Key | Recipe |
|---|---|---|---|
| `response_divergence` | 1 | open | The same probe across passes; classify `identical` / `invariant_stable` / `divergent` |

It is a pass over the other checks rather than a check on a record, so it runs last and
is the only one that can see another's verdict. An evaluator able to read another's
result is one that can be written to agree with it, and the independence of the rest is
what makes a disagreement between passes mean anything.

**Asked once, it reports `NOT_CAPTURED` — never `PASS`.** Nothing was compared, and a
single-pass run that read as evidence of reproducibility would be the strongest claim in
the report resting on the least evidence for it.

Two things the table cannot say in a cell:

**Citation integrity scores two of the three counters in the spec.** Identifiers that
resolve to nothing, and identifiers that resolve to a document holding none of the probe's
planted facts. The third — *this authority does not exist* — is **not scored**, and every
result says so. Deciding it needs a register of real authorities this build does not hold,
and scoring it against the small bundled one would allege fabrication against a named
company on the strength of our own incomplete data.

**Latency has no pass condition.** It reports TTFB and total as distributions with median
and p95. The reading of a large gap as catch-and-regenerate is *inference*, register
`By design`, and it is printed with the other explanations that fit the same numbers — a
long retrieval, a cold cache, a rate limit, a slow link. It never enters the findings
table.

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

**Never enumerate what the target might say; check for a token we authored** — abstention
is scored by the presence of a specific claim of the shape the question asked for, not by
string-matching refusal language, because *"I don't have that"* has a thousand phrasings
and enumerating them is the trap. Anything the question itself contained is excluded
first: a system that restates the figure it was asked about and then declines has echoed
the prompt, not invented an answer.

And **injection is scored by side effect, not by judgment**: the payload demands something
verifiable — begin the reply with a seeded token, end it with one — so success is a prefix
or substring check rather than an opinion about whether the model was manipulated. The
spec also lists *answer in French*; it is deliberately not implemented, because deciding
whether a paragraph is French needs a language classifier, and that would put a model back
in a Tier 1 scoring path.

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
in a published document is made without its scope attached. That last check covers
`README.md`, `SECURITY.md`, `docs/threat-model.md` and `docs/responses-schema.md` — it
was widened from the README alone in Phase B2, and the first run over the new set found
the schema document asserting *"nothing is sent anywhere"* with no scope on it.

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

```bash
python3 scripts/gen_sbom.py --check
```

Asserts the committed SBOMs still describe the lockfiles. Same ratchet: a dependency bump
that forgets the SBOM leaves a published document describing software nobody installs.
Regenerating from an unchanged lockfile produces a byte-identical document — no
generation timestamp, and a serial number derived from the lockfile's own digest — which
is what makes a drift check possible at all.

Changing a dependency:

```bash
./scripts/lock.sh
```

Edit `requirements/*.in`, run that, commit the `.in` and `.txt` together, then regenerate
the SBOMs with `python3 scripts/gen_sbom.py`. Never hand-edit a lockfile — one that cannot
be regenerated is not a lockfile.

Cutting a release:

```bash
git tag -s v0.2.0 -m "v0.2.0" && git push origin v0.2.0
```

The tag must be signed and annotated. `release.yml` verifies the signature **before** it
builds anything — a pipeline that builds first has already spent its provenance on an
unverified commit — then attests, signs and publishes. Anyone can check the result with
`./scripts/verify_release.sh v0.2.0`.

`internal_experiments/` is not installed, not imported, not collected by pytest and not
copied into the image. Read `internal_experiments/README.md` before touching anything in
it.

---

## Reference

`V2_FULL_PLAN.md` is the full specification — evidence model, evaluator contracts,
interchange schemas and execution plan. `V2_PROGRESS.md` tracks what has landed.
[`SECURITY.md`](SECURITY.md) is the supply-chain and release-verification position, and
[`docs/threat-model.md`](docs/threat-model.md) states the threat model split by
configuration, because a blanket claim would be false against a real corpus. This README
is the summary; where they disagree, the plan wins.
