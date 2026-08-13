# Why it is built this way

The README says what the tool does. This says why each of the awkward decisions was taken,
because every one of them costs something and a reader who does not know the cost cannot
tell a considered design from an arbitrary one.

---

## The dependency split

`sentence-transformers` pulls torch and transformers — hundreds of transitive packages
nobody can review. That is fine on our machine and unacceptable on a target's.

| Mode | Dependencies |
|---|---|
| `generate`, `validate` | `httpx`, `pyyaml`, `pydantic`, `jsonpath-ng`, `websockets` — five pure-Python libraries |
| `score` | the above, plus `sentence-transformers`, `torch` (CPU), a pinned NLI model |

CI asserts the boundary: the `generate` entrypoint imports and runs in a virtualenv
installed without the `[score]` extra, and `torch` is not importable there. *"Read it in
ten minutes"* is then literally true rather than a slogan.

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

## The Key column: what is published, and what is sealed for a few hours

Nothing about the **method** is withheld, ever. The code, the check recipes in the
README, the schemas and the scoring rules are public and forkable. The only artefact with a timing rule on it
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
in the output. Those nine are sealed — for the length of a run.

**Eight of the nineteen checks are published with their answer keys, nine are sealed, and
two are conditional.** For the sealed nine, telling you the value we are testing whether
you retrieved would test nothing.

Every report prints the key beside each check and counts them, so the withholding is a
bounded fact on the page rather than an atmosphere.

---

## Why anything is sealed at all

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

---

## Two design rules

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

## Evaluator boundaries and dependency design

### Citation integrity scoring boundaries

`citation_integrity` scores two of the three counters in the specification:
1. Document identifiers that resolve to nothing.
2. Document identifiers that resolve to a document holding none of the probe's planted facts.

The third counter — *this authority does not exist* — is deliberately **not scored**. Verifying non-existence requires an exhaustive register of primary legal authorities. Scoring against an incomplete bundled register would risk alleging fabrication against a target based on missing benchmark entries.

### Latency measurement parameters

`latency` has no pass/fail condition. It reports TTFB and total duration as distributions with median and p95. A large disparity between TTFB and total duration may indicate regeneration or filtering; in the report this is classified as `By design` inference alongside alternative explanations (slow retrieval, cold caches, network throttling). It is never entered into the defect findings table.

### Exact dependency pinning without version ranges

Version ranges are omitted across all configuration files. Third-party reproducibility requires reconstructing identical environments from the manifest and signed commits. Version ranges allow unpinned transitive updates, converting security audits into statements about installation date rather than the committed artefact (as occurred with `idna` 3.11 / PYSEC-2026-215).

With `--require-hashes`, substituted or modified packages fail installation immediately.

### Security scanner isolation

Security scanners (`pip-audit`, Bandit, Semgrep, Trivy) are isolated in a dedicated fourth layer (`requirements/audit.txt`) rather than merged into development dependencies. This prevents transitive package explosion in standard contributor workflows while maintaining strict CI gating.

---

## Capability map

The v2 migration is complete: every capability below is in the code, and the table is kept
as a map of the surface rather than as a promissory note. Nothing here is waiting to be
built.

| Capability | Status |
|---|---|
| Local-only scoring; no third-party inference path | **Shipped** |
| Exact version pins + hash-pinned lockfiles, split by mode | **Shipped** — four layers, cross-checked for agreement |
| CycloneDX SBOM per dependency layer | **Shipped** — generated from the lockfiles, drift-gated |
| Public CI: tests, gates, `pip-audit` / Bandit / Semgrep / Trivy | **Shipped** — actions pinned by commit SHA |
| Signed releases: GPG tag, SLSA provenance, cosign | **Shipped** — `scripts/verify_release.sh` is the reader's half |
| Corpus verified before a run starts; loud abort, no report on failure | **Shipped** |
| 19 evaluators against a configured endpoint | **Shipped** — all rewritten to the §8.2 recipes |
| Licensed-content reproduction check (§8.2 #18) | **Shipped** — identifiers only; `in_index` / `external_fetch` / `unattributed` never collapsed |
| SSE / WebSocket transport, JSONPath extraction | **Shipped** |
| JSON report with per-check counts and tiers | **Shipped** — published contract, `report.v2` |
| Markdown attestation, evidence bundle, Tier 2 distributions | **Shipped** |
| Non-root containers, base pinned by digest, deps under `--require-hashes` | **Shipped** — two images along the dependency boundary, signed by digest, `trivy image` per image |
| `validate` / `generate` / `score` mode split; scoring offline and enforced | **Shipped** |
| `responses.jsonl` interchange format + published schema | **Shipped** |
| Tier 1 / Tier 2 tagging and tier-separated findings | **Shipped** — 17 Tier 1, 2 Tier 2 |
| Run manifest: hashes, commit SHA, model versions, seed, corpus mode, battery composition | **Shipped** |
| `hash` handover record; `score` refuses a ground truth that moved | **Shipped** |
| `NOT_ELIGIBLE` / `NOT_CAPTURED` statuses | **Shipped** |
| Authorisation gating on injection / canary families | **Shipped** — `generate` aborts before sending anything; production needs a second, typed act |
| Seeded plant generation with collision guard | **Shipped** — `plant`, 29 invariants across 15 documents |
| Two-phase corpus upload for index freshness | **Shipped** |
| N-pass execution and variance as a first-class finding | **Shipped** — `response_divergence`, Tier 1 |
| Pathological reference target, sensitivity/specificity CI gates | **Shipped** — 20 profiles over both batteries, [matrix published](harness-verification.md) |
| Existing-corpus mode and point-in-time probe pairs | **Shipped** — no `upload` endpoint needed; anchors quoted from `legislation.gov.uk` |
| Domain corpus library, versioned, with staleness triggers | **Shipped** — 3 corpora; a corpus that omits a spine role does not load |

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

## Field evaluations and empirical instrument revisions

The existing-corpus battery has been executed against live production legal-AI products under ordinary-use conditions (unauthenticated public or trial access, no adversarial uploads, no canaries, scoring against statutory quotations from `legislation.gov.uk`).

### Target findings observed in field runs

- **Temporal transition edge-cases**: Probes targeting statutory figures one month prior to legislative amendment exposed divergent behaviors: anticipating future rates prematurely, conversational routing dropouts, and explanatory dual-version returns.
- **Non-reproducible reasoning**: Single-pass correctness masked underlying instability where identical dated questions failed on subsequent passes despite sound reasoning on the successful pass.
- **Transport-level dropouts**: Systems returned conversational greetings in place of substantive answers across multiple passes despite verified payload delivery.
- **Generative phrasing variance vs. divergence**: Stable multi-system responses with differing prose were verified as invariant-stable without triggering false divergence findings.

### Instrument modifications derived from field data

1. **Prose anchor retirement**: Free-form prose anchors were replaced with strict invariant tokens after semantically identical correct answers scored false negatives due to paraphrase variations.
2. **Jurisdiction scoping for licensed content**: Jurisdictional qualifiers were added to licensed-content probes to prevent multi-jurisdictional engines from answering via foreign statutes and passing.
3. **Native asynchronous transport support**: Submit-and-poll async transport was implemented natively to eliminate wrapper scripts.
