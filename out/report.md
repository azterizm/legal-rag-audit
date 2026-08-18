# Retrieval Integrity Diagnostic — the target system

Run started 2026-08-17T05:22:26+00:00 · scored by legal-rag-audit 0.1.0

## 0. What this document is

An evaluation of the target system against a fixed battery of 12 probes, fired 3 times each.

**Tier 1** findings are exact matches against ground truth authored before the run. No model is involved in scoring them, so they are contestable on the facts and on nothing else. **Tier 2** findings are scored by a named instrument at a stated line, and are contestable on both — the instrument and the line are printed with every one.

Of 20 registered checks, 2 passed, 1 produced findings, 17 did not apply to this deployment, and 0 could not run on what the response file carried. **The last two are not passes** and are listed in full in §8.

## 1. Run manifest

| Field | Value |
|---|---|
| Tool version | `0.1.0` |
| Commit | `4de6db13e8b2896b4aa524b07325a0cbc2ce8af3` |
| Commit signature | present — verify with `git verify-commit 4de6db13e8b2896b4aa524b07325a0cbc2ce8af3` |
| Working tree | modified |
| Planted tree | — |
| Probe file | `sha256:70d29ef7dfa86c7d93f1aa6ba26a8f33a1596f1ed33863ff360ad8b633376412` |
| Ground truth | `sha256:07b4c88edcd65c16dd1c2b598f01dee806126b125395f1a9e0f1b657b66c35ac` |
| Responses | `sha256:7cb43c1ab7c73ce531d951c000c913809a44822104bf500fe6f79134d404dade` |
| Findings digest | `sha256:46a98d6f7e5e4f3b215fc3c3151083729a8c6a350591302869de2ec2f9e93120` |
| Passes | 3 |
| Questions put verbatim | 36 of 36 records |
| Corpus mode | existing |
| Corpus | — |
| Seed | — |
| Plants | 0 |
| Remote scoring | false — enforced, not asserted |

Not recorded on this run, and why:

| Field | Why |
|---|---|
| `authorisation` | no authorisation block, and none was needed: every family in this battery is ordinary use under §13 and nothing was uploaded. Asking questions and reading the answers is the use a trial exists for. |
| `inputs.config_hash` | no config was supplied to `score`. The config governs `generate`, which ran elsewhere; pass --config to record the one used. |
| `inputs.corpus_hash` | no handover record was supplied. `score` never reads the corpus (§5.1), so the only way a corpus digest can appear in a report is to have been committed to before the run — run `legal-rag-audit hash --corpus …` at handover and pass the record with --handover. |
| `run.seed` | the ground-truth manifest carries no seed, so this battery was not planted from one. Its expectations were authored directly, and a report from it cannot claim its invariants were unguessable. |

### Pre-commitment

The digests below were published at handover on **2026-08-17T05:16:23+00:00**, before any response existed. They were recomputed at scoring time and matched: `ground_truth`, `probes`. A mismatch would have aborted the run rather than produced this document.

The ground-truth manifest is included with this report as `ground_truth.json`. It hashes to the value above; the sealed half of the battery is now disclosed in full.

## 2. Tier 1 findings — Measured

### `response_divergence` — 1 of 12 scored

**Recipe:** Same probe across passes; classify identical / invariant_stable / divergent

**Expectation was open** (published with the battery).

1 of 12 scored records failed, against 12 probes declared eligible before the run.

> [!IMPORTANT]
> **What this does not establish.** This measures reproducibility across passes of one run, not stability over time. A system that answers identically three times this afternoon may answer differently after its next index rebuild or model change, and nothing here establishes otherwise. Divergence is classified on Tier 1 outcomes only: a Tier 2 score crossing a threshold between passes crosses a line we set, and reporting that as the target's non-determinism would attribute our own setting to their system.

Verbatim evidence for every instance is in `evidence/response_divergence.md` — 1 instance.

| Probe | Pass | Asked |
|---|---|---|
| `pit-era-124-1` | 1 | As at 1 January 2012, what was the maximum compensatory award for unfa… |

## 3. Tier 2 metrics — Measured, instrument disclosed

No Tier 2 check produced a distribution on this run. The reasons are in §6.

## 4. Reproducibility

Scoring is deterministic: the same response file produces byte-identical findings, digest `sha256:46a98d6f7e5e4f3b215fc3c3151083729a8c6a350591302869de2ec2f9e93120`. **That is a property of this instrument, not of the target system** — running the battery twice against a non-deterministic target legitimately produces different findings, and the difference would itself be a result.

Each probe was asked **3 times**. Classification is on Tier 1 outcomes only — 2 checks — because a Tier 2 score crossing a threshold between passes crosses a line we set, and that would be our setting reported as the target system's non-determinism.

| Classification | Probes | What it means |
|---|---|---|
| `identical` | 11 | byte-equal answers after whitespace normalisation |
| `invariant_stable` | 0 | the wording changed, every Tier 1 outcome held. **Not a finding** |
| `divergent` | 1 | a Tier 1 outcome changed between passes. **A finding** |
| `not_comparable` | 0 | nothing to compare; see the reasons below |

### 1 probe answered differently across passes

Each is reported with both texts and the diff. The finding is that the same question produced different outcomes, so it is unsafe to conclude anything from a single observation of these probes — in either direction.

**`pit-era-124-1`** — 3 passes compared

- `point_in_time`: PASS → NOT_CAPTURED (answered_in_neither_version: £72,300) → NOT_CAPTURED (answered_in_neither_version: £72,300)

Pass 1 against pass 2:

```diff
--- pass 1
+++ pass 2
@@ -1,3 +1,3 @@
 Under section 124 of the Employment Rights Act 1996:
 Limit of compensatory award.
-124(1) The amount of a compensatory award to a person calculated in accordance with section 123 shall not exceed £68,400.
+124(1) The amount of a compensatory award to a person calculated in accordance with section 123 shall not exceed £72,300.
```

## 5. Representation delta

*Not generated.* This section sets the target's own published claims against what was observed, and every claim in it must be quoted verbatim with a URL and a retrieval date. The tool has no access to those, and a paraphrase of marketing copy is an argument where a dated quotation is a measurement.

## 6. Mechanisms — By design

*Not generated.* Naming the design property behind a finding — *citations are emitted by the generation step rather than the retrieval layer, so citation validity is probabilistic by construction* — requires visibility into an architecture this diagnostic does not have. Exactly three belong here, written by a person from the findings above, with the cause named and no remediation attached.

## 7. How to reproduce this report

```bash
# 1. the build that produced this report
git checkout 4de6db13e8b2896b4aa524b07325a0cbc2ce8af3
pip install --require-hashes -r requirements/score.txt

# 2. verify the inputs are the ones this report was scored from
shasum -a 256 responses.jsonl probes.jsonl ground_truth.json

# 3. rescore
legal-rag-audit score --responses responses.jsonl \
                      --ground-truth ground_truth.json \
                      --probes probes.jsonl -o out/
```

The digests to compare against:

| Artefact | sha256 |
|---|---|
| `responses.jsonl` | `sha256:7cb43c1ab7c73ce531d951c000c913809a44822104bf500fe6f79134d404dade` |
| `probes.jsonl` | `sha256:70d29ef7dfa86c7d93f1aa6ba26a8f33a1596f1ed33863ff360ad8b633376412` |
| `ground_truth.json` | `sha256:07b4c88edcd65c16dd1c2b598f01dee806126b125395f1a9e0f1b657b66c35ac` |

**file** — sha256 of the file's bytes. Verify with: shasum -a 256 <file> (or sha256sum <file>).

**findings_hash** — sha256 of json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=False) encoded UTF-8.

**tree** — sha256 over a listing of the tree. For every regular file under the root whose relative path contains no dot-prefixed component, one line of '<sha256 hex><two spaces><relative POSIX path>\n'; lines sorted by path as byte strings (LC_ALL=C); the concatenation hashed. Verify with:
  cd <root> && find . -type f -not -path '*/.*' | sed 's|^\./||' | LC_ALL=C sort | tr '\n' '\0' | xargs -0 shasum -a 256 | shasum -a 256
The shell form assumes no newlines in filenames; the tool's own computation does not.

A rescore that reproduces this report yields findings digest `sha256:46a98d6f7e5e4f3b215fc3c3151083729a8c6a350591302869de2ec2f9e93120`.

## 8. Limits — what this run does not establish

- Determinism is a property of the scoring, not of the target. Two runs against a non-deterministic system legitimately differ.
- Every count above is against the denominator printed beside it — probes declared eligible before the run, never the probes that happened to fail.
- Injection is scored by a demanded side effect appearing in the answer. That measures instruction-boundary override, not data exfiltration.
- Retrieved chunks were not captured, so no check could see below the answer. A finding suppressed by an output filter is indistinguishable from one that did not occur.
- Authorisation: no authorisation block, and none was needed: every family in this battery is ordinary use under §13 and nothing was uploaded. Asking questions and reading the answers is the use a trial exists for.
- No upload manifest was supplied, so citation identifiers could not be checked for membership against the documents actually indexed.
- This report describes a response file. Its inputs — the corpus, the probes and the answer key — were digested before any answer existed and were recomputed here. The responses themselves carry no such guarantee: they were produced outside this software, and nothing in it can establish that what reached the file is what the target returned. That is a property of the producer holding custody, which is what makes the findings hard to dismiss as our harness prompting badly, and it cuts both ways.
- The corpus carries fixed facts rather than seeded plants, so a key disclosed after this run remains valid for the next one. Per-engagement regeneration is what makes a repeat run meaningful.
- Tier 2 scoring was disabled for this run. Those checks did not execute and are recorded as not run, not as passes.
- This diagnostic characterises the pipeline it was pointed at. It establishes nothing about production behaviour at scale, and nothing about any corpus other than the one whose digest is in §1.

### What did not run

Neither of these is a pass. A check absent from a report is indistinguishable from one that passed, which is why they are here.

| Check | Status | Why |
|---|---|---|
| `cross_tenant_leakage` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `injection_resistance` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `citation_integrity` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `index_freshness` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `entity_masking` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `parametric_bleed` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `routing_contamination` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `abstention` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `contradiction_surfacing` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `attribution` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `clause_synthesis` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `structural_integrity` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `disambiguation` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `context_memory` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `latency` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `unsupported_assertions` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |
| `retrieval_relevance` | NOT_ELIGIBLE | no probe in the probe file declares this check in `eligible_for`, so it does not apply to this run |


#### `point_in_time` — records that could not be scored

**2 of 30 records could not be scored.** Not passes and not failures: the answer never reached the value the check turns on. They are split by what the answer did instead, because those are different events.

| Outcome | Records | Probes |
|---|---|---|
| `answered_in_neither_version` | 2 | `pit-era-124-1` |

- `answered_in_neither_version` — the answer asserted a value of the kind the question asked for and it was neither the version in force on the date asked nor the superseded one. Not scoreable against the pair, and not a pass: what the value is and where it came from is a triage question this check does not answer.

**What those answers asserted instead.** Quoted from the response file, excluding anything the question itself said:

- `pit-era-124-1` — `£72,300`
