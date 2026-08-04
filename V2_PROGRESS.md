# legal-rag-audit v2 — execution progress

Tracks [V2_FULL_PLAN.md](V2_FULL_PLAN.md) §17. One section per phase. Each phase records
what landed, what was deliberately deferred, and how the acceptance criteria were checked
— because "acceptance passed" with no record of how is the same class of claim this tool
exists to measure in other people's systems.

**Status legend:** ✅ complete · 🟡 in progress · ⬜ not started

| Phase | Deliverable | Effort | Status |
|---|---|---|---|
| **A** | Remove the remote-scoring path; rescope README claims | 0.5 d | ✅ 2026-08-01 |
| **A+** | Exact/hash-pinned dependencies; corpus packaging + guardrail | — | ✅ 2026-08-01 |
| **B** | `responses.jsonl` schema + offline `score` + probe/response spec + dependency split | 3 d | ✅ 2026-08-01 *(two Dockerfiles deferred with Docker)* |
| **B2** | Hardened invocation, SBOM, signed tags + SLSA + cosign, CI scanning | 1 d | ✅ 2026-08-03 *(cosign signs blobs; image signing ships with the image split)* |
| **C** | Tier tagging + report v2 + manifest/hashing + GPG-signed releases | 2.5 d | ✅ 2026-08-02 *(signed releases are Phase B2; Docker deferred)* |
| **D** | Seeded plant generation + collision guard; rewrite evaluators 4–14 | 4 d | ✅ 2026-08-03 |
| **E** | N-pass execution + variance reporting | 1 d | ✅ 2026-08-04 *(profiles are response files; the live mock target is F2)* |
| **F** | `validate` mode | 0.5 d | ✅ 2026-08-04 |
| **F2** | Pathological reference target + sensitivity/specificity gates | 1.5 d | ⬜ |
| **G** | Existing-corpus mode + point-in-time pairs + licensed-content reproduction | 4–5 d | ⬜ |
| **H** | Reposition bundled corpus as demo; first domain corpus | 2.5 d | ⬜ |
| **I** | Authorisation controls + retention position | 0.5 d | ⬜ |

Minimum sellable cut is **A + B + C + F + I + one domain corpus (H)**.

---

## Phase A — decontaminate ✅

Closes defect 1 in §19: the remote-scoring path contradicted both the determinism claim
and the zero-exfiltration claim, and until it was gone every other claim in the README
was contaminated by it.

### What was there

The contradiction was live, not theoretical.

- `--use-gemini` / `--gemini-model` were real CLI flags, threaded through `TestRunner`
  into four evaluators.
- Three evaluators POSTed corpus text and target answers to
  `generativelanguage.googleapis.com`: `hallucination.py`, `retrieval.py`,
  `confidence.py`. On that path a third party is a sub-processor and every run is a
  data-transfer event.
- The hallucination path issued **three generation calls per claim and averaged the
  scores**. Same responses in, different report out — §4.2(a) exactly.
- `conflict.py` carried `use_gemini` / `gemini_model` constructor parameters it never
  read.
- The remote paths imported `requests`, which appeared in neither `pyproject.toml` nor
  `requirements.txt` — an undeclared runtime dependency reachable only from the path that
  was being denied.

### What landed

**Code**

- Remote scoring removed from `legal_rag_audit/` entirely. `HallucinationEvaluator`,
  `RetrievalEvaluator` and `ConfidenceEvaluator` now take a model name only; the
  branching, the vendor calls and the dead parameters are gone.
- `--use-gemini` and `--gemini-model` removed from the CLI. The surface is now
  `-c/--config`, `-o/--output`, `--skip-upload`, `-v/--verbose`.
- Removed an unused `numpy` import from `hallucination.py` — another undeclared
  dependency reference.
- Declared `tqdm`, which the local scoring path genuinely uses and which was riding in
  transitively via `sentence-transformers`.
- `requirements.txt` reorganised along the §5.3 mode boundary, so the Phase B split has
  an obvious seam.

**Quarantine, per §4.2 option 2**

- `internal_experiments/remote_scoring/gemini.py` holds the removed code as three plain
  functions, with the non-determinism and sub-processor properties documented at the top.
- `internal_experiments/README.md` states the exclusion mechanism and the conditions on
  ever using it again: claims rescoped in the same paragraph, `remote_scoring: true` in
  the manifest, findings segregated into Tier 2, and it never enters the published path.
- Exclusion is enforced four ways: explicit `packages = [...]` in `pyproject.toml` (not
  discovery), `.dockerignore`, `norecursedirs` so pytest never collects it, and the
  acceptance script.
- The two root-level `test_gemini_*.py` files were not tests — they needed a live API key
  and printed to stdout, while sitting where pytest would collect them. Moved and renamed
  to `manual_*_check.py`.

**Acceptance gates, as executable checks rather than one-time verification**

- `scripts/check_no_remote_scoring.sh` — vendor markers, HTTP-client imports in the
  scoring path, wheel exclusion, image exclusion, README claims.
- `scripts/check_readme_claims.py` — Appendix D, enforced **per paragraph**, because
  §4.2 requires scoping to sit in the same paragraph as the claim rather than in a
  footnote.
- `tests/test_no_remote_scoring.py` — 78 tests, the first repository tests.

**README** — rewritten to the v2 register (tiers, counts-not-percentages, three modes,
mechanical check names, hardened invocation, limits, authorisation boundary), with an
**Implementation status** table marking every specified-but-unbuilt capability. Writing a
README that describes `validate`/`generate`/`score` as if they exist would have been the
same defect Phase A is closing.

### Acceptance

| Criterion | Result |
|---|---|
| `grep -ri "gemini\|openai\|api_key" src/` clean | ✅ adapted — see note below |
| README contains no unqualified determinism or exfiltration claim | ✅ enforced per paragraph by `check_readme_claims.py` |
| `pip-audit` clean | ✅ 49 packages, full declared set, fresh resolution; see note |
| Package still imports and the CLI surface is intact | ✅ `--use-gemini` / `--gemini-model` gone; `-c`, `-o`, `--skip-upload`, `-v` remain |
| `pytest` | ✅ 78 passed |
| Built wheel contains no vendor marker and no `internal_experiments/` | ✅ inspected the actual `.whl`, not the config that produces it |
| Local scoring path still works after the surgery | ✅ real inference through `RetrievalEvaluator`; three identical runs on the same input |

All four gate checks were **negative-controlled** — each was made to fail on purpose
(unqualified determinism, unscoped exfiltration claim, banned vocabulary, a vendor marker
planted in an evaluator) and each fired before the change was reverted. A gate that has
never failed is decoration.

### Two adaptations, recorded rather than silent

1. **The grep pattern.** `api_key` cannot be excluded literally: §6.1 of the plan itself
   mandates `auth.type: api_key` and `token_env: TARGET_API_KEY` for authenticating to
   the *target*, which is the system under test, not a scoring sub-processor. The gate
   matches vendor credential names explicitly instead (`GEMINI_API_KEY`,
   `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`), plus vendor names, vendor endpoints and the
   removed flag spellings. Nothing is lost and the exclusion is documented in the script.
2. **`src/` layout.** The plan's §5.2 tree is `src/legal_rag_audit/`; at the time this
   gate was written the package was still at the repository root. Resolved at the start
   of Phase B — the gate now scans `src/legal_rag_audit/`.

### Note on `pip-audit`

Clean: a fresh resolution of the **full** declared set — 49 packages, generate and score
paths together, including `torch` and `transformers` — reports no known vulnerabilities.
The generate/validate subset (15 packages) is clean on its own.

One thing the audit surfaced that is worth keeping visible. This machine's existing
environment carries `idna==3.11` (PYSEC-2026-215, fixed in 3.15), reached transitively
through `httpx`; a fresh install resolves `idna==3.18` and is unaffected. Nothing in the
declared set pins a vulnerable version — but nothing pins a safe one either. **This is
exactly the gap Phase B2 closes.** An unpinned `>=` requirement means the audit result
depends on when you installed, which is not a property a reproducibility claim can rest
on. Until the hash-pinned lockfile lands, `pip-audit` describes a moment rather than the
artefact, and the two results above differ only because they were resolved on different
days.

### Deferred out of Phase A, deliberately

- **`docs/limits.md` as a file.** The limits are in the README as a section; the `docs/`
  tree arrives with Phase B.
- **Config key renames.** `thresholds` → `display_thresholds`, and the `hallucination_rate`
  key → mechanical names, are Phase C. The README states plainly that the current numbers
  are settings rather than standards, and why the rename is coming.
- **The abstention evaluator's refusal list.** `ConfidenceEvaluator` still enumerates
  canonical refusal phrasings, which §8.2 #8 identifies as the trap the design exists to
  avoid. The limitation is now documented in the class docstring; the inverted rewrite is
  Phase D.
- **`ContradictionSurfacingEvaluator` outcome split.** Both-present vs exactly-one-present
  are collapsed into PASS/FAIL. §8.2 #9 wants them distinguished and the silently-picked
  side recorded. Noted in the code; Phase D.
- **Dockerfile split.** One image still installs the full dependency set including
  `pytest`. `.dockerignore` now exists and excludes the quarantine, secrets, run output
  and planning documents. The two-image split is Phase B.

### Found while verifying

**The bundled corpus was not in the wheel.** Inspecting the built artefact showed
`legal_rag_audit/corpus/*.txt` absent: `pyproject.toml` declared no `package-data`, so
setuptools shipped only `.py` files. Fixed in A+ below.

**Repository hygiene**, worth clearing before a public tag:

- `legal_rag_audit.egg-info/` and `output.log` are git-tracked build/run artefacts.
  `.gitignore` covers `*.egg-info/`, but tracking predates it.
- `check_nli.py` and `scratch_json.py` are scratch scripts at the repository root.
- `PLAN.md` is staged for deletion; `V1_PLAN.md` is untracked.

---

## Phase A+ — dependency pinning and corpus integrity ✅

Two items pulled forward on request. Neither is a full phase: the pinning is the lockfile
half of B2, and the corpus fix closes the defect found while verifying Phase A.

### Exact, hash-pinned dependencies

Nothing is loose anywhere. Ranges made three claims untrue at once — NF11 said a third
party reconstructs the run from the manifest and a signed commit, but `>=` resolves to
different software depending on the day; a Tier 2 threshold is meaningless without the
model and library version behind it; and `pip-audit` described a moment rather than the
artefact, which is how `idna==3.11` (PYSEC-2026-215) was installed here while the declared
set looked clean.

**Structure** — three layers along the §5.3 mode boundary, `.in` authored and `.txt`
generated:

| Layer | Packages | Role |
|---|---|---|
| `requirements/generate.txt` | 14 | `generate`/`validate` runtime. No ML stack |
| `requirements/score.txt` | 66 | adds local scoring models |
| `requirements/dev.txt` | 92 | adds test and release tooling |

- **Universal resolution** (`uv pip compile --universal`) — one lockfile installs on macOS
  arm64 and Linux x86_64, with the differences carried as environment markers.
  Per-platform lockfiles would silently disagree with each other.
- **Hashes on every entry** (`--generate-hashes`, installed with `--require-hashes`). A
  pin fixes the version; a hash fixes the bytes. A substituted artefact fails the install
  rather than reaching a run.
- `pyproject.toml` pins exactly too, so `pip install -e .` gives the same versions without
  hash verification.
- `scripts/lock.sh` regenerates. `scripts/check_pins.py` asserts nothing is loose, every
  entry is hashed, and `pyproject.toml` agrees with the lockfiles — two sources of truth
  that disagree are worse than one that is vague, because the disagreement is silent.
- The Dockerfile now installs the dependency layer under `--require-hashes`, installs the
  package with `--no-deps` so the lockfile stays the only source of versions, and runs
  non-root.
- Top-level `requirements.txt` removed; `requires-python` raised to `>=3.11` per §5.4.

**Verified:** both lockfiles install hash-verified into clean virtualenvs (`generate` 14
packages, `score` 47 applicable on this platform out of 66 marker-gated). `pip-audit`
clean on both. `torch`, `transformers`, `sentence_transformers` and `numpy` are all
confirmed *absent* from the generate environment, and `config`, `client` and
`corpus_loader` import there with no ML stack present — §5.3's boundary now has a real
test behind it rather than an intention.

**Still open in B2:** SBOM, GPG-signed tags, cosign, SLSA provenance, public CI scanning,
base-image digest pinning (a tag is mutable, so `python:3.11-slim` is a pin in name only),
and CPU-only torch — the current lock takes default torch, which pulls CUDA packages under
Linux markers.

### Corpus packaging and guardrail

Two different defects, fixed together.

**Packaging.** `[tool.setuptools.package-data]` now ships `corpus/*.txt` and `corpus/*.md`.
Verified by building the wheel and opening it: 13 of 13 documents present, then installed
non-editable into a clean virtualenv and loaded from site-packages. Testing the config
that produces an artefact is not testing the artefact.

**Behaviour.** The silent fallback is gone. `legal_rag_audit/corpus_loader.py` resolves and
verifies the corpus before the first request and raises `CorpusError`; the CLI prints the
diagnosis and exits 2 **without writing a report**. Checks: bundled corpus installed and
all 13 documents present (naming any that are missing), custom `path` set and non-empty,
every document UTF-8 and non-empty, hidden files skipped, and sorted document order so the
corpus reads identically on every machine.

Why it mattered more than the packaging bug: with the corpus absent the runner substituted
two hard-coded stand-in documents and *completed*. The report then described a 2-document
corpus while the config said thirteen, and nothing on the page disclosed the substitution.
A setup problem rendering as a finding is exactly what NF9 forbids, and it is the failure
class this tool sells against.

The bundled corpus stays what it is — a generic demo so someone can try the harness on a
best case. Real engagements run a domain corpus authored per target (§9.4, §9.5). The
guardrail is about the corpus being present and readable, not about it being right for
anyone's jurisdiction.

### Acceptance

| Criterion | Result |
|---|---|
| No loose specifier in `pyproject.toml` or any lockfile | ✅ |
| Every lockfile entry carries hashes | ✅ |
| Lockfiles install under `--require-hashes` | ✅ both layers, clean virtualenvs |
| `pip-audit` on the installed pinned sets | ✅ clean |
| ML stack unreachable from the generate layer | ✅ asserted against a real install |
| Bundled corpus present in the built wheel | ✅ 13/13, wheel opened and inspected |
| Missing corpus aborts with a diagnosis, writes no report | ✅ exit 2, verified through the CLI |
| `pytest` | ✅ 113 passed |

Negative-controlled as before: a loosened pin, a version drift between `pyproject.toml`
and the lockfile, and a lockfile entry with its hashes stripped each made the gate fail
before being reverted.

### Not verified

**The Dockerfile changes are not build-tested** — Docker is not available on this machine.
The `--require-hashes` install, the `--no-deps` package install and the non-root user are
written but unproven. Build it before relying on it.

---

## Phase B — the interchange split ✅

**Acceptance (§17.2):** `score` runs offline ✅ · `generate` runs in a venv without torch
✅ · a third party produces a conforming `responses.jsonl` from the doc alone ✅ ·
golden-report test passes byte-identical twice ✅ · two Dockerfiles ⬜ *(deferred with the
rest of Docker)*.

### What came apart

The v1 runner held each probe next to its own answer key — the query string and the
strings a correct answer must contain, in the same function, a few lines apart. That is
workable when one process does both and it is precisely what has to separate for a target
to run the battery themselves.

| Artefact | Carries | Goes to |
|---|---|---|
| `probes.jsonl` (`probes.v1`) | questions + `eligible_for` | them |
| `responses.jsonl` (`responses.v1`) | what came back, verbatim | them → us |
| `ground_truth.json` (`ground_truth.v1`) | expectations | withheld, hashed at handover |

`demo_battery.py` holds all three in one authoring table and emits them through separate
functions. `build_probes()` cannot see the expectations, so a probe file that leaks an
answer key is not something a caller can ask for.

### Packages

```
src/legal_rag_audit/
├── interchange/     pydantic records + generated JSON Schemas (both sides of §5.1)
├── probes/          the demo battery; questions and expectations, emitted separately
├── transport/       httpx / SSE / WS — generate only
├── generate/        fires the battery, writes responses.jsonl, scores nothing
├── score/           offline; registry, driver, socket enforcement
└── evaluators/      unchanged internals, now lazily imported
```

Moved to `src/` first, in its own commit. Under a flat layout `import legal_rag_audit`
from the repository root resolves to the working tree whether or not the package is
installed, which made the wheel and venv tests weaker than they looked.

### Three rules the format exists to enforce

1. **Absence is recorded, not inferred.** `citations: null` means *not captured*; `[]`
   means *the target returned none*. Collapsing them turns "we did not look" into "it
   cited nothing", which is a finding that would have to be withdrawn.
2. **A transport failure is not a result.** A record with `error` set is `NOT_CAPTURED`
   for every check. The v1 runner scored an empty answer as a failing test — a 502
   rendered as a hallucination finding, which is NF9 exactly inverted.
3. **An unknown schema version is refused, not parsed.** A guessed reading produces a
   report indistinguishable from one we understood (NF10).

Parse errors name file and line, because the person fixing them may not have our code.

### Statuses, and the one that does the work

`NOT_ELIGIBLE` — no probe declared the check; it does not apply to this deployment.
`NOT_CAPTURED` — probes were eligible, the file lacks what the check reads. Neither is a
pass, both are printed. Denominators come from `eligible_for`, fixed before the run
(F39); a response for a probe absent from the probe file is refused rather than added to
a denominator after the fact.

### The registry records the implemented tier, not the intended one

§8.1 puts `abstention` in Tier 1 once Phase D rewrites it as an inverted presence check.
It runs a cross-encoder today, so it is registered **Tier 2**. Labelling it Tier 1 before
the model leaves the path would be the same class of claim Phase A removed. Currently
**14 Tier 1, 3 Tier 2**, and a test asserts the Tier 2 count equals the number of
evaluators that load a model.

### Found while building it

**Four defects in the demo battery, two of which would have failed a correct system.**

- `contradiction_surfacing` expected `$2M` and `$5M`. Both are in the corpus — as two
  lines of the *insurance schedule* inside one agreement. Different policies, not
  conflicting caps. Now scored against the real conflict: v1 §11.3 carves data breaches
  out of the cap entirely, v2 §11.3 pulls them back inside a 12-month cap.
- `index_freshness` required `$10M`, which exists only as a Tier 2 *asset threshold* in
  an unrelated financial regulation. A system that read the documents failed; one that
  echoed the figure from the question passed. The check needs a two-phase upload
  `generate` does not perform, so no probe declares it and the report says
  `NOT_ELIGIBLE` with the reason. §14.2 makes a false positive a release blocker, and an
  unsatisfiable expectation is one.
- `disambiguation` required `"hazardous waste"` and `structural_integrity` required
  `"tier 2"` — both phrases in their own questions. An expectation satisfiable by echoing
  the prompt tests nothing about retrieval. Structural integrity now rests on the
  adjacency check, which echoing cannot satisfy and which also distinguishes the
  `$250,000` in the penalty table from an unrelated one elsewhere in the corpus.

A test now fails on any `must_contain` token appearing in its own probe text. Two
exemptions, enumerated with reasons: injection, where the payload must contain the token
it is scored on, and one premise-loaded probe where the false figure is the trap.

**`chat()` failed whenever `endpoints.chat` was a plain URL string** — the form the
README example uses. It read `.headers` off the union unconditionally. Uploads take the
same union and handle it, so the corpus uploaded cleanly and then all seventeen probes
came back as transport errors, which reads like an unreachable target rather than our
bug. Found by running `generate` end to end against a stub, not by a unit test.

**The wheel shipped no `probes`, `score`, `generate` or `transport` package.** The
explicit `packages` list keeps `internal_experiments/` out and silently drops anything
new. Found by the venv test; the list is now compared against what is on disk.

**`score()` left network enforcement on for the whole process.** Correct for the CLI,
wrong for an importable function — a caller who scored one file found networking broken
afterwards. Now scoped to the call. Found by running the suite together; every test
passed in isolation.

### Acceptance

| Claim | How it was checked |
|---|---|
| `score` opens no sockets | AST walk proves no module reachable from `score` imports `transport` or `generate`, with a negative control; `socket`, `create_connection` and `getaddrinfo` each raise under enforcement |
| `generate` runs without torch | A real virtualenv built from `requirements/generate.txt`: `torch`, `transformers`, `sentence_transformers`, `numpy` all absent while `generate`, the CLI and Tier 1 scoring run |
| A third party can produce the file | The curl+jq example is **extracted from `docs/responses-schema.md` and executed** against a stub, and the file it writes is scored |
| Byte-identical rescoring | Same inputs scored twice, compared as bytes (NF2) |
| Denominators from the probe file | Every check's `eligible` equals the count declared in `eligible_for` |
| Degradation is explicit | Missing chunks, missing upload manifest, missing records and transport errors each produce `NOT_CAPTURED`, never `PASS` |
| Base install is the generate layer | `check_pins.py` asserts every base dependency resolves in `requirements/generate.txt`; negative-controlled |
| Published schemas match the models | Generated by `scripts/gen_schemas.py`, `--check` fails on drift |

**240 tests.** Four gates clean.

### Deliberately not done in Phase B

- **Two Dockerfiles.** Deferred with the rest of Docker, at your instruction.
- **`validate` mode.** Phase F.
- **Markdown attestation.** `score` writes `report.json`; the attestation document is
  Phase C (§10.6). `report.py` was deleted rather than left unreachable — its Markdown
  writer led with a hallucination-rate percentage, which Appendix D bans as a headline.
- **Full §6.1 config v2.** The dead `tests:` section is gone, because check selection now
  comes from `eligible_for` and a config that still listed seventeen booleans would let
  someone disable a check and watch it run. `version: 2`, the transport block, the
  `authorisation` block (Phase I) and the `display_thresholds` rename (Phase C) stay in
  their own phases.
- **Real TTFB.** The transport reads the full body before returning, so time to first
  byte is not observable. `ttfb_ms` is null and the latency check reports that only total
  time was compared — v1 recorded total under both names, which made the TTFB-to-total
  gap a comparison of a number with itself.
- **`legacy_params`.** Six checks still take arguments in their own shapes (PII pairs,
  fact/source tuples, the latency probe pairing). Named so they cannot be mistaken for
  part of the durable contract; Phase D folds them into the §8.2 recipes.

---

## Plan amendment — the withheld half is half, and disclosure is enforced

**Question raised:** does withholding `ground_truth.json` read as manufactured mystique?
Showing everything demonstrates competence; withholding invites the reading that the
opacity is deliberate.

**Answer, and the correction.** The premise was that the manifest is obfuscated and only
we can read it. It is not. §3.6 already required shipping it in full with the report; the
withholding is a *timing* rule lasting the length of a run, and the direction it protects
is the one people assume backwards. The vendor tuning to an early key is the obvious
risk. The damaging one is the accusation pointed at us — *"you decided what counted as a
failure after you saw the failure"* — which is unanswerable without a hash published
before any response existed, and which voids every finding in the document. The
pre-commitment constrains the auditor more than the vendor.

**But the objection had real force**, and the plan overstated what secrecy buys by
treating the manifest as one undifferentiated sealed object. It is not one thing.

### §3.6.1 — the split, on a mechanical criterion

> A check is **disclosable** when knowing its expectation in advance cannot help a target
> pass it without exhibiting the behaviour under test.

That tracks §8.1's inverted/positive split, for the same underlying reason. An inverted
expectation — *this token must not appear* — can only be satisfied by not emitting the
token, which is the behaviour being measured; a vendor who reads the key and stops
leaking has passed, not gamed. A positive expectation — *this token must appear* — can be
pinned, cached or prompted with no retrieval improvement, invisibly.

**8 open, 8 held, 2 conditional.** The conditional pair (`cross_tenant_leakage`,
`licensed_content_reproduction`) is inverted but scored on a literal string an output
filter could suppress; capturing `retrieved_chunks` moves detection below that layer and
opens them. That is a concrete benefit to offer for exposing retrieval.

The open half becomes the free published battery (§9.4), and the withholding becomes one
sentence rather than a policy: *eight of eighteen ship with their answer keys; the other
eight test whether you retrieved a value, and telling you the value first would test
nothing.*

### Where secrecy is not the durable property

Per-engagement seeded plants (Phase D) mean a key disclosed after run *n* is worthless
for run *n+1*. Withholding buys hours; **regeneration** is what makes a repeat engagement
meaningful. A design depending on a key staying secret indefinitely would be fragile in
exactly the way §1.3 forbids.

### Landed in code, not only in the plan

- `CheckSpec.key` — `open` / `held` / `conditional`, with `key_for(chunks_captured)`
  resolving the conditional pair against what the response file carried.
- Every check prints its key in `report.json`; the summary counts `published_keys` and
  `withheld_keys`, so the withholding is a bounded number on the page.
- Tests assert the registry's classification matches §3.6.1 name for name, that chunk
  capture opens the conditional check, and — the criterion itself — that **no purely
  inverted expectation is ever marked withheld**, since withholding one buys nothing and
  costs the openness.
- README gains a Key column and the two sections that answer the objection where a buyer
  reads it.

### New requirement — F44, disclosure enforced by the tool

§3.6's disclosure half was an undertaking in a document with nothing implementing it.
Phase C acceptance now requires `score` to write the ground-truth manifest into the output
directory beside the report and record its hash in the run manifest, with a test asserting
the written copy hashes to the recorded value. Disclosure becomes a property of the tool.

**Since built.** See the Phase C section below — the pre-commitment mechanism is now
operable, and F44 is enforced by a test rather than by a paragraph.

---

## Plan amendment — evaluator 18, licensed-content reproduction

**Date: 2026-08-01.** Specification only. No code; the check lands with Phase G.

*"Do you hold rights to all content in your index?"* is a standard TPRM question, and one
of the very few where this harness can return evidence rather than a policy answer.
Ingesting a commercial publisher's edition into a vector index is a different act from
querying it per seat, and the 17 evaluators had no probe for it.

**Why it is Tier 1.** The publisher's editorial layer — headnotes, Key Numbers, star
pagination, citation numbers, signal marks — does not exist in the primary source. Its
presence in a response is an exact-match check with no model anywhere in the path. The
identifier class is additionally safe for us to hold and to quote: publisher-assigned
strings are identifiers, not protected expression.

**Where the compliance question actually sits** is *where the content lives*, not whether
it was ever lawfully read. So the check scores three outcomes and never collapses them:
`in_index` (marker in `retrieved_chunks`, or in an answer attributed to an internal
document — their retriever returned it), `external_fetch` (marker cited to the publisher's
own service — consistent with licensed per-query access, recorded as an outcome and not a
finding), and `unattributed` (no citation, no retrieval evidence — `NOT_CAPTURED`, and
never a licensing finding).

**Two properties worth noting.**

It is **existing-corpus only**. We cannot plant licensed content — planting it would be
the infringement we are asking about. That makes it the strongest argument yet for F25
being Must: it needs `chat` and nothing else.

It is **structural but free-runnable**, which §16.2 says the structural class is not.
Asking a question and reading the answer is ordinary use, so it needs no upload, no second
account, no authorisation and no automation — while still saying something about
architecture rather than about a rate. On a public trial it belongs in the 10–15 queries
alongside non-determinism.

**The controlling risk, and the control.** A finding here alleges unlawful conduct by a
named company if it is written carelessly, which is a worse failure than a retracted
metric. Presence in an index is **not** a licence breach — the vendor may hold a
bulk-ingestion or content-partnership agreement, and no run can see their contracts. A
mandatory limit line is printed with every instance, `external_fetch` never counts as a
finding, and the wording names what a procurement reviewer will ask rather than asserting
infringement.

### Edits made to V2_FULL_PLAN.md

§8.1 row 18 · §8.2 full contract · §3.4 sufficiency (1 instance) · §6.6 report JSON shape ·
§9.2 existing-corpus ground truth · §10.5 mechanical names · §11.2 F43 (Must) · §13
ordinary-use class · §14.1 `serve_licensed_content` profile · §14.2 sensitivity gate ·
§16.1 free-tier boundary · §16.2 the exception and its caution · §17.1/§17.2 Phase G
(effort 3–4 d → 4–5 d) · §18 v0.4.0 · §20.1 items 7 and 8 · §20.2 risk row · Appendix A
"editorial layer" · Appendix B. Counts propagated everywhere they were asserted.

**One sequencing defect found and fixed while propagating.** The sensitivity gate was
written as a fixed number. Raising it to 18/18 would have made it unmeetable at v0.3.0,
because Phase F2 ships the reference target while evaluator 18 arrives in Phase G. It is
now expressed as *every shipped evaluator* — 17/17 at v0.3.0, 18/18 at v0.4.0 — and the
plan specifies the gate be written against the evaluator registry rather than a constant,
so shipping an evaluator without a pathology profile fails the build instead of quietly
shrinking the denominator.

### Open, and needed before Phase G

- **§20.1 item 7 — how licensed reference material is held without our doing the thing we
  are asking about.** Resolution: ship the identifier class only. The editorial-prose
  class needs a licence we would have to hold; where a paid engagement warrants it, match
  by shingle hash so no licensed text is stored, and quote at most a short excerpt.
- **§20.1 item 8 — publisher and jurisdiction coverage at launch.** Bound it to the two
  target practice areas. A partial marker set is honest if the report says which
  publishers were checked; an implied claim of full coverage is not.

### README

Evaluator table extended to 18, `licensed_content_reproduction` added to the mechanical
check names, the "presence is not a breach" limit added to the Limits section, and the
marker check added to the ordinary-use column of the authorisation table. It is marked
**Specified — v0.4.0** in the implementation-status table; the "17 evaluators" row stays
as it is, because 17 is what currently runs.

---

## Phase C (part 1) — the pre-commitment, made operable ✅

**Date: 2026-08-02.** The `hash` subcommand (F38), the run manifest emitter (§6.5, F23)
and the disclosure writer (F44). The rest of Phase C — the `report.v2.schema.json`
writer, the Markdown attestation (§10.6), the evidence bundle (F41) and Tier 2
distributions (F24) — is still outstanding.

The reason this came before the report writer: §3.6 was the one argument in the whole
document with nothing implementing it. A method that *says* it pre-commits and does not
is weaker than one that never claimed to, because the claim is checkable and the check
fails.

### The mechanism is now a precondition, not an undertaking

Three commands, and the join between them is the point:

```bash
legal-rag-audit hash --corpus ./corpus/ --probes probes.jsonl \
                     --ground-truth ground_truth.json -o handover.json
legal-rag-audit generate -c config.yaml -o responses.jsonl
legal-rag-audit score --responses responses.jsonl --ground-truth ground_truth.json \
                      --probes probes.jsonl --handover handover.json -o out/
```

`score --handover` recomputes the digests and **aborts on a mismatch** — exit 2, no
report, nothing written. Not a warning in the manifest, not a flag on the page. A report
produced from a key that changed after the responses came back cannot be told apart from
one produced honestly, which is the entire reason the digest was published first. If the
tool would emit it with a caveat, the caveat is the only thing standing between us and
the accusation, and a caveat is not a control.

The corpus is the exception and is labelled as one: `score` reads no corpus (§5.1), so
its digest is *carried* from the handover record with `corpus_hash_provenance` saying
so. A manifest that presented a carried value as a computed one would overclaim in
exactly the direction this section exists to prevent.

### The digests are recomputable without this software

A hash only our tool can reproduce is a hash nobody checks. Every digest ships with its
recipe, in the handover record and in the manifest:

- **Files** — plain SHA-256 of the bytes. `shasum -a 256 <file>`.
- **Trees** — SHA-256 over a listing of `<hex>  <relative path>` lines, sorted as byte
  strings, dot-prefixed paths excluded. The recipe string carries the shell pipeline that
  reproduces it, and `tests/test_manifest.py` **executes that pipeline** and compares it
  to the tool's answer. If the two ever diverge, the instruction we printed in a handover
  document is false, which is worse than printing none.

The dot-file exclusion is a real decision with a real cost — a dot-file inside a corpus
is outside the commitment. It is worth paying: a `.DS_Store` dropped in by Finder would
otherwise change the digest of a corpus nobody touched, and a pre-commitment that fires
on filesystem noise trains people to ignore it.

### What the manifest refuses to leave out

The §6.5 checklist is in code as `REQUIRED_BY_SECTION_6_5`, and `unrecorded_gaps()`
asserts every field is either populated or explained in `not_recorded`. This build cannot
know four of them, and says so in the artefact rather than omitting them:

| Field | Why it is null |
|---|---|
| `run.seed` | Nothing here is seeded. Seeded planting is Phase D; the demo corpus carries fixed facts, and recording a seed would describe a step that did not happen |
| `run.corpus_mode` | Not established by `score`, which reads no corpus. Phase D records it when `plant` produces one |
| `inputs.corpus_hash` | Only knowable from a handover record. Populated when `--handover` is passed |
| `authorisation` | The §13 block is not in the config yet (Phase I). This run asserts nothing about consent |

Same rule as F40, applied to provenance: an omitted field and an unknown value read
identically on the page and are different statements.

### Two decisions worth arguing with

**The manifest reports whether the commit is signed. It does not verify the signature.**
Verification means `git log --pretty=%G?`, which invokes gpg in a child process, and a
gpg configured with `auto-key-retrieve` fetches missing keys from a keyserver. `score`
runs inside `offline()`, which patches *this* process's sockets and cannot see a child's
— so a verifying manifest would carry a network path on the inside of the guarantee this
project makes most loudly (§5.1, F18). Reading the commit object's `gpgsig` header is a
local object read and needs no gpg at all. The manifest records presence, the sha, and
`git verify-commit <sha>` for the reader to run. That is also the better artefact:
"we checked our own signature and it was fine" is not evidence to anyone deciding whether
to trust us. A test pins the git subcommands to `rev-parse`, `cat-file` and `status`.

**Tier 2 model names are duplicated in `instruments.py` rather than read off the
evaluators.** The manifest must state which model *would have* scored a check on a
`--skip-tier2` run, and reading the name off the class would import sentence-transformers
— and therefore torch — to write a manifest for a run that loaded no models at all. The
duplication is checked by an AST reader that parses the evaluator sources without
importing them, so the drift test runs in the torch-free environment the duplication
exists to serve.

### NF2 was narrowed, deliberately

The report now carries a manifest with `started` and `finished`, so "the same inputs
produce a byte-identical report" can no longer be literally true. The claim is now about
the findings: `findings_of(report)` drops the manifest, and `manifest.scoring.findings_hash`
is the digest of what remains.

This was already a latent flake. The old test passed only because two runs landed inside
the same second — it would have failed on a slow machine at a second boundary. The
findings digest replaces "diff the two files" with one string to compare, which is also
the form a client can check.

### Found while building it

- **A signature check inside the offline region.** The first version ran
  `git log --pretty=%G?`. Caught before commit; see above.
- **The determinism tests were passing on the clock.** Same-second timestamps made them
  pass and hid the narrowing. Now explicit, with a test that the digest actually moves
  when an answer changes — a hash that never changes proves nothing about what it covers.
- **`abstention` has an undisclosed threshold.** `registry.py` calls
  `ConfidenceEvaluator.evaluate()` with no threshold, so the evaluator's own `0.5`
  applies and nothing in the config can change it. Now in the manifest as
  `"threshold_source": "evaluator default — not configurable in this build"`. §4.1 says a
  Tier 2 threshold must be recorded; an operator-invisible one is the case that most
  needed recording.
- **Model weights are not pinned.** The library version is pinned; the checkpoint is
  resolved by name at load time, so a re-run months later could load different weights
  under the same name. Recorded as `weights_revision: null` with the reason. Not fixed
  here — it needs a revision-pinning mechanism, and pretending otherwise in the manifest
  would be the overclaim this section is about.

### Acceptance

| Claim | How it was checked |
|---|---|
| The published tree recipe is the one the tool uses | The shell pipeline from `TREE_RECIPE` is executed with `shasum` and compared to `hash_tree()` |
| A ground truth that moved aborts the run | Tamper the file after `hash`, score with `--handover`: `PreCommitmentError`, exit 2, no output directory |
| The abort can be argued with | The message carries both digests, the path, and the handover timestamp |
| Every run discloses the ground truth (F44) | `out/ground_truth.json` exists and hashes to `ground_truth_manifest_hash`; byte-identical to the input |
| The manifest has no silent holes | `unrecorded_gaps()` is empty on a real run, and a negative control proves it can fail |
| Every Tier 2 number names its instrument | Model, threshold, threshold source and kind present for all three, on a `--skip-tier2` run |
| Provenance opens no network path | AST walk pins the git subcommands to local object reads |
| The instrument table has not drifted | Evaluator defaults read by AST, without importing torch |
| Battery composition is declared, not derived | Per-check counts equal `eligible_for` counts from the probe file |
| Findings are still deterministic | `findings_of` byte-identical across two runs; digest equal; digest moves when an answer changes |

**305 tests.** Four gates clean.

### Deliberately not done

- **`report.v2.schema.json` writer, Markdown attestation, evidence bundle, Tier 2
  distributions.** The rest of Phase C.
- **Model revision pinning.** Recorded as a gap in the manifest, not solved.
- **The `authorisation` block.** Phase I owns the gate; recording a block the config
  cannot express would be a field that is always null for no stated reason.
- **Signing the release artefacts.** Phase B2. The manifest records the commit; cosign,
  SLSA and SBOM are a separate piece of work, and Docker stays deferred at your
  instruction.

---

## Phase C (part 2) — the report ✅

**Date: 2026-08-02.** `report.v2` as a published contract, the Markdown attestation
(§10.6), the evidence bundle (F41) and Tier 2 distributions (F24). Phase C is complete
apart from signed release artefacts, which belong to B2.

A scoring run now writes a whole handover document rather than a JSON file:

```
out/
  report.json        the evidence — a published contract
  report.md          the testimony — §10.1 order, deal-enders first
  manifest.json      provenance, also embedded in report.json
  ground_truth.json  the sealed half, disclosed (F44)
  evidence/          verbatim excerpts per Tier 1 finding (F41)
```

### One deviation from §6.6, and the reason

The sketch nests checks under `tier1` and `tier2`. Shipped, they are keyed by name,
with `tier1` / `tier2` as ordered *lists of names* carrying §10.1's reading order.

Nesting makes a check's address depend on its tier — and the tier is expected to
change. `abstention` is registered Tier 2 today because the shipped implementation runs
a cross-encoder over refusal phrasings; §8.1 puts it in Tier 1 once Phase D rewrites it
as an inverted check. A consumer whose path to a check breaks because we improved how
it is scored would be right to complain.

### The evidence bundle distinguishes two failures that are not the same

- **A token appeared that should not have.** The evidence is a 160-character window of
  the answer around the match, with the offset. Short, exact, disputable.
- **A token that should have appeared did not.** There is no excerpt to take. The whole
  answer is reproduced, because the claim is about everything the system *did* say —
  calling a fragment an "excerpt" would imply we chose it, and a reader would be right
  to ask what was in the rest.

Attribution turned out to be a third shape and is handled as such: an *orphaned claim*
is a fact that appeared without its source, so the absent string is the source marker,
not the fact. Taking every string in the row would have named the correctly attributed
facts as absent.

Tier 1 only. Tier 2 evidence is the distribution — quoting a sentence a model scored
0.83 would dress a threshold decision as an observation.

### Tier 2 distributions (F24)

Ten buckets across [0, 1], **fixed rather than fitted to the observed range**, because
buckets that move with the data make two runs of the same check incomparable and
comparability is the reason for printing a distribution at all. The line is marked on
the correct side per instrument — `retrieval_relevance` passes at or above,
`unsupported_assertions` at or below — and every distribution states that the line is a
setting of this run rather than a published standard.

The number is read by a key declared in `instruments.py` rather than guessed, because
the three evaluators call it three different things (`score`, `avg_similarity`,
`max_similarity`). A test asserts each evaluator still emits its declared key: if one
is renamed, every Tier 2 distribution silently empties and nothing else fails.

### What the attestation will not write

§5 (representation delta) and §6 (mechanisms) are marked placeholders. The delta needs
their published claims quoted with a URL and a retrieval date; the mechanism section
needs an architectural reading. Neither is available to the tool, and generating either
would be the failure this project exists to measure in other people's systems. The
document says so in place of guessing, which is also the more useful instruction to the
person who has to write them.

### Found while building it

- **The findings digest would have been unrecomputable.** The first version hashed the
  raw check dicts and told the reader to hash the published document. The models fill
  in absent optional fields as nulls, so the two differ for every check that ran
  cleanly — the recipe printed in §7 of the attestation would have been a false
  instruction, which is worse than printing none. `build_findings()` now serialises
  through the models *before* hashing, and a test asserts
  `hash_json(findings_of(report))` equals the recorded digest.
- **The attestation makes a promise; a test now checks it.** §7 states the findings
  digest a rescore will produce. A test rescores and compares. That section is where a
  sceptical reader goes first, and a wrong number there discredits the document.
- **`citations_captured` is three-valued and the model made it two.** `None` means *the
  file does not say* — a response file where every record happens to carry null
  citations is indistinguishable from one whose producer never looked. Coercing it to
  `false` in the report would have claimed knowledge we do not have.
- **Two defects in the rendered document**, found by reading the output rather than the
  tests: a cross-reference to §6 for a section that was §7, and section numbering that
  drifted from the §10.6 skeleton. The not-tested list now sits inside Limits, which is
  where the skeleton puts it, restoring 0–8.
- **`cache.py` has no quotable evidence.** `CacheInvalidationEvaluator` returns
  `has_stale_data` / `has_fresh_data` as booleans and never echoes the tokens it was
  given, so `index_freshness` instances fall back to reproducing the whole answer. It
  is exempted by name with that reason, not silently. Phase D's rewrite is where the
  tokens come back.

### Acceptance

| Claim | How it was checked |
|---|---|
| A report from a failing profile leads with Tier 1 and quotes it | End-to-end run with planted leaks; `evidence/cross_tenant_leakage.md` carries the canary in context with its offset |
| A clean profile reads as a defensible attestation with a real not-tested section | Single-probe clean run: "No Tier 1 check produced a finding", and every `NOT_ELIGIBLE` / `NOT_CAPTURED` check still on the page under "Neither of these is a pass" |
| The findings digest is recomputable from the published document | `hash_json(findings_of(report))` equals `manifest.scoring.findings_hash` |
| §7's reproduction promise holds | Rescore, compare against the digest the document printed |
| No headline rate anywhere in the attestation | Regex over the rendered document finds no `%` |
| No invented mechanism | §6 is a marked placeholder; asserted |
| Tier 2 lines are marked on the correct side | Both directions tested against their real instruments |
| Buckets are comparable between runs | Tight and spread distributions produce identical bucket ranges |
| Distribution keys have not drifted | AST reads each evaluator's emitted string constants without importing torch |
| Every failing evaluator contributes evidence | AST walk over all evaluators; exemptions are named with reasons |
| The report matches its published schema | Generated from the model; every required field asserted present in a real report |

**353 tests.** Four gates clean.

### Deliberately not done

- **Signed release artefacts.** Phase B2 — SBOM, cosign, SLSA. The manifest records the
  commit and hands over `git verify-commit`; that is as far as this phase goes.
- **The `display_thresholds` rename.** The distributions now carry the "setting, not a
  standard" statement on every Tier 2 result, which was the substance of it. The rename
  is cosmetic by comparison and belongs with the §6.1 config v2 work.
- **Variance across passes.** §10.6 §4 says so on the page when `passes` is 1. Phase E.
- **Docker**, still deferred at your instruction.

---

## Phase D — Tier 1 conversion ✅

**2026-08-03.** Every Tier 1 expectation is now a plant: minted from a run seed,
collision-guarded, inserted at a declared location. Evaluators 2 and 4–14 rewritten to the
§8.2 recipes. Abstention moved to Tier 1 by taking the model out of it, which is the count
§8.1 has always claimed — 15 of the 18 evaluators, with #18 arriving in Phase G to make 16.

### The plants

`plants/` is four modules and one idea: **never enumerate what the target might say; check
for a token we authored.**

Every value is `HMAC-SHA256(seed, "<plant_id>#<attempt>")`, read as a stream of
rejection-sampled 32-bit integers and formatted per kind. Six kinds — entity, label,
figure, date, citation, opaque token — each chosen because it survives paraphrase. The
recipe is published in prose as well as in code, and a test reimplements the stream from
the prose and compares, for the same reason the tree-hash recipe is executed as a shell
pipeline: the person checking us may not be running our code, and may deliberately not be.

`attempt` exists because the collision guard rejects values, and §3.2 says a rejected
plant regenerates from `plant_id + n` rather than being nudged into shape by hand. The
accepted attempt is recorded on every plant, so regenerating the battery from the seed
needs no search.

### The guard, and what it says it cannot do

Tier 1 says *a planted token either appeared or it did not*. That is true only while the
token means one thing, and three things stop it meaning one thing:

1. **The value already occurs in the corpus** — its presence then proves the system read a
   document, not that it leaked one. Checked against the templates *before* planting;
   afterwards every plant is in the corpus by construction.
2. **Two plants overlap** — every hit on one is a hit on the other and the report names the
   wrong document. Checked in both directions, because presence is scored by substring.
3. **A generated citation resolves to a real authority** — the finding then dies the
   moment somebody produces the case, and it dies about a named company.

The third is the one that cannot be closed offline, and the guard says so rather than
implying otherwise. It checks coined party names against a bundled register of real
parties and common surnames, and it requires every generated neutral citation to carry a
number at or above 4000 — outside the range any division of the High Court has issued in a
year, so the check holds without a lookup. `CHECKED` and `NOT_CHECKED` both go into every
ground-truth manifest verbatim. A reader told a corpus was "guarded" has been told nothing;
a reader told no lookup left the machine can price the residual themselves. §20.2 closes it
with manual review of the generated citations in the first corpus of each domain, and that
review belongs in the report, not in the code.

**Exhaustion is loud.** After 64 regenerations the guard aborts and names the kind whose
space ran out. `date` has the smallest space by nature — 28 × 12 × 46 — and a guard that
quietly returned a duplicate would break Tier 1 with nothing failing.

### Evaluators — what the rewrite actually changed

Four of these were producing findings that could not have survived being argued with.

- **Latency failed records.** A contradictory query taking three times the baseline, or
  exceeding a 30-second ceiling, produced `latency: FAIL` in the Tier 1 table. That is a
  claim about somebody's architecture derived from two numbers and three constants we
  chose, and a vendor answers it by pointing at their egress. It is now a measurement with
  no pass condition: distributions with median and p95, and the catch-and-regenerate
  reading printed separately under register `By design` **with the other explanations that
  fit the same numbers** — a long retrieval, a cold cache, a rate limit, a slow link.
- **Disambiguation failed on latency too**, for the same reason, in a check about
  retrieval. Removed; the timing is recorded beside the verdict and cannot change it.
- **Parametric bleed failed vague answers.** A verdict called `UNCITED_RESPONSE` failed any
  answer that neither refused in one of nine enumerated phrasings nor contained a known
  fact — a finding manufactured from the absence of our own vocabulary. Both the regex list
  and the verdict are gone. Citing a live source is now a recorded outcome, not a failure,
  detected by a URL because that is the only form of "cited a source" that does not require
  reading intent.
- **Attribution accepted the identifier anywhere in the answer.** An answer stating the
  figure in one paragraph and the document three paragraphs later scored as attributed. Now
  scored by sentence unit (§20.1 item 1), with the segmenter taught not to split
  *Donoghue v. Stevenson* at the `v.`

And the one that moved tiers: **abstention** ran a cross-encoder over five canonical
refusals and asked whether the answer entailed one of them. A model in the path, a
contestable 0.5, and — worse — a system declining in an unusual phrasing scored as a
failure. It is now the presence of a *specific claim of the shape the question asked for*:
a currency figure, a date, a neutral citation, a percentage, a duration. Deliberately not a
bare integer, because *"I searched 13 documents"* is not a fabricated claim. Anything the
question itself contained is excluded first, so a system that restates the figure it was
asked about and then declines is not recorded as having invented it.

### One result shape, and the defect class it removes

Every Tier 1 evaluator now returns through `_common.result`, which always emits `appeared`
and `absent`. The evidence bundle reads those two keys and nothing else.

Before this it read an enumerated list of nine key names — `leaked_content`,
`trigger_phrases_found`, `missing_facts` and six more — half of them nested under
`details`. Enumeration rots silently: an evaluator gains a field, nobody adds it, and the
bundle falls back to reproducing whole answers for a check that had a token all along. That
is exactly what had happened to `cache.py`, which named its evidence `has_stale_data` and
had to be exempted by hand in a test with a note saying Phase D would fix it. The fix was
not another key in the list; it was removing the list.

### Three schema versions, all breaking, all for the same phase

- `probes.v2` — `phase`, saying whether a probe is asked before or after the corpus
  revision. Index freshness cannot be scored without it: *not yet indexed* and *never
  invalidated* are different findings.
- `responses.v2` — `revision_wait_seconds` on the capture notes, for the same reason. Only
  the elapsed time separates the two.
- `ground_truth.v2` — `legacy_params` folded away. Four evaluators used to take arguments
  in shapes of their own, carried in a free-form dict; each now has a named field, and
  `adjacency` became a list because two checks need more than one pairing.

A superseded identifier is still refused — a guessed reading is the failure NF10 exists to
prevent — but the refusal now names what replaced it and why. A correct refusal that reads
as a bug is a support conversation nobody needed.

### The two-phase upload

`plant` writes `corpus/base/` and `corpus/revision/`; `generate` uploads the base, asks the
`initial` probes, replaces the revised documents, waits, and asks the `after_revision`
ones. Both states are sealed by one tree digest, because splitting them would let the
revised value be chosen after the first phase's answers came back.

Where the revision cannot happen — no upload endpoint, `--skip-upload` — the second-phase
probes are **not asked**, and the capture notes say why. Asking them against an unchanged
corpus and reading the unchanged answer as a stale index would be a finding manufactured
from the target's constraints.

### `plant`, a fifth command

§7 lists three modes and they are about *who runs what*. Planting sits on our side beside
`hash`, so it does not add a party to the engagement — but it exists as a command for the
same reason `hash` does: a pipeline step that only ever ran inside another command could
not be inspected, repeated, or checked by the client.

With no `--seed` it uses a **published** demo seed and says so, on the command line and in
the report's manifest table and limits section. A battery anyone can regenerate is right
for a demonstration and wrong for an engagement, and the difference has to be visible on
the page rather than inferred from a document count.

### Found while building it

- **`statute_alpha.txt` did not match "statute alpha".** The identifier-opening helper
  replaced separators but kept the extension, so adjacency compared against
  `statute alpha txt`. A test written from the recipe caught it; nothing else would have,
  and the symptom would have been orphaned-claim findings against a system attributing
  correctly.
- **`£0,729,530.68`.** The figure minter drew its leading digit from 0–9. A plant that
  looks like a formatting bug invites the reply that the finding is one.
- **`Trulkune Nominees Ltd` as the name of a support band.** Entity plants carry a legal
  form, which reads as a planting bug in a service schedule. Added a `label` kind — a
  coined word with no form — for defined terms, bands and namespaces.
- **The manifest was still saying seed and corpus mode arrive in Phase D**, in a run that
  had both. They come off the ground-truth manifest now, which is the one artefact `score`
  reads that knows how the corpus was made.
- **The mandated limit lines were not on the page.** §8.2 requires the injection finding to
  be published alongside the sentence saying what it does not establish. The registry
  carried it and the attestation never printed it. Found by reading the rendered Markdown,
  which is the second phase running where a test did not.
- **`entity_masking` findings had no outcome line** in the evidence bundle, because that
  evaluator concludes several at once and reports `outcomes` rather than `outcome`. All of
  them are printed now: an answer that both swapped a counterparty and omitted an entity
  did two things, and naming one would understate it.

### Acceptance

| Claim | How it was checked |
|---|---|
| 10,000 generations, no collision | `test_ten_thousand_generations_produce_no_collision` — guarded mint across four kinds, asserting uniqueness of every value |
| No plant occurs in the corpus as authored | 1,000 generations checked against the concatenated templates |
| Every Tier 1 evaluator references no model | AST over every non-Tier-2 evaluator module; fails on any import of torch, transformers, sentence-transformers, numpy or sklearn |
| 15 Tier 1 evaluators shipped | Asserted against the registry, in the torch-free venv |
| The published mint recipe matches the implementation | Independent reimplementation of the stream from the prose, compared draw for draw |
| Generated citations cannot resolve to a real authority | 300 citations checked for a neutral number ≥ 4000; 500 checked against the bundled register |
| Exhaustion is loud | Guard forced to exhaustion; asserts `PlantExhausted` naming the kind |
| Every declared plant is in the corpus and every slot is filled | Round-trip over the planted corpus; both failure directions tested |
| Injection is scored by side effect | Prefix, suffix, and a token in the wrong position — which passes and is recorded |
| Abstention passes any phrasing of a refusal | Four phrasings including an empty answer; and a figure echoed from the question |
| Latency cannot fail | A 900-second record scores PASS with the measurement recorded |
| Adjacency needs one sentence | Same sentence passes, adjacent sentences fail, unsegmentable is NOT_CAPTURED |
| A clean run produces no findings | Answers built from the planted values; zero findings across all 17 checks |

**442 tests.** Four gates clean.

### Deliberately not done

- **Counter (b) of citation integrity** — *this authority does not exist*. It needs a
  register of real authorities, which is external ground truth arriving in Phase G. Scoring
  it against the small bundled register would manufacture an allegation of fabrication out
  of our own incomplete data, and §14.2 makes a false positive a release blocker. Every
  result carries the reason.
- **Answer-in-French as an injection payload.** §3.3 lists it. Deciding whether a paragraph
  is French needs a language classifier, which would put a model back in a Tier 1 path.
- **Tier 2 fallback for unsegmentable answers.** §8.2 #10 allows degrading to Tier 2 when
  sentence segmentation fails. This reports `NOT_CAPTURED` with the reason instead — the
  conservative half. A per-answer tier switch would mean one check produced Tier 1 and
  Tier 2 results in the same run, and no reader could be expected to track that.
- **Namespace scoping in the transport.** `route-001` records `scoped_to: null`, and the
  evaluator reports `retrieval_contamination` rather than `namespace_breach`. Both are
  worth reporting; only the first is a boundary failure, and printing the stronger sentence
  for both would overstate half the findings.
- **Multi-turn context memory.** `mem-001` uses an anaphor with a defined antecedent inside
  one question. True multi-turn resolution needs a session-capable transport the
  interchange format does not yet carry.
- **The bundled 13-document corpus.** Still shipped, still checked for completeness, no
  longer the battery's corpus. §9.4 gives Phase H the job of deciding what it becomes; this
  phase did not pre-empt it by deleting it.
- **Docker**, still deferred at your instruction.

---

## Plan amendment — the artefact route, named and made structural (F45)

**2026-08-03.** The route where the target keeps their endpoint entirely and returns a
file was a *property* of the mode split (§5.1) and a *preference* in the access ladder
(§15.3 item 2). It was never a named configuration, so nothing could reference it, nothing
stated what it costs, and nothing tested that it stays available.

It is now §5.1.1 with a requirement id, and the plan's modes table shows what was always
true and never written down: **four of the five modes never touch a network, and the one
that does is the only optional one.**

### What the amendment added

- **§5.1.1** — the route, what the client holds, what they return, what it costs and what
  it does not. The costs are two, and neither weakens a finding: capture completeness is
  theirs to declare (already `NOT_CAPTURED` on the page, never a pass), and the two-phase
  probes need them to apply the revision. What it *strengthens* is the part worth selling
  — responses their harness produced cannot be answered with *"your tool prompted it
  wrong."*
- **F45** — the route must never require endpoint access. `plant`, `hash` and `score`
  import nothing from `transport/`.
- **§14.3** — two acceptance rows, and both are tested rather than asserted.
- **§15.3 item 2** — say it before rung 3, not after. It removes the security review, the
  credential request and the config from the critical path in one move.

### The gap it surfaced, and the fix

The pre-commitment had an open end. Hashing the probe file fixes **which questions were to
be asked**; nothing checked whether they were. On this route nobody watched them go out,
so *"the battery was fired as written"* was an undertaking — the same shape §3.6 closed at
the other end for the answer key, left open at this one.

`score` now compares every record's `query` against the sealed probe text:

| Outcome | What happens |
|---|---|
| **verbatim** | Counted in the manifest, printed in §1 as *"Questions put verbatim — n of m records"* |
| **wrapped** — the probe text sits inside a longer query | The finding stands, because it is the same question. The claim that it was put verbatim does not, and §8 names the probes |
| **absent** — the query does not contain the probe text | Aborts (NF9). The record answers a different question, and scoring it would produce a finding about something nobody asked |

Whitespace is normalised first, so a harness that re-wraps long lines is not recorded as
wrapping the question. Noise in a section that exists to carry signal is the same defect
as no section at all.

### And the limit the route cannot close

Nothing in this software can establish that what reached the file is what the target
returned. That is now a line in every report's §8 rather than something the reader has to
work out. The guarantee on this route comes from the producer holding custody — and a
guarantee that runs in their favour runs in ours too, which is why it is printed rather
than hedged.

### Acceptance

| Claim | How it was checked |
|---|---|
| The whole route runs with no transport installed | `plant` → `hash` → hand-written `responses.jsonl` → `score`, in the generate-layer venv with `httpx` uninstalled. 17 checks reported, pre-commitment verified, report written |
| A wrapped question is named, not passed off | A system preamble around one probe; asserted named in the manifest and still producing a verdict |
| A different question aborts | Asserted, and the message carries both texts so the diff is in the error rather than in a support conversation |
| Re-wrapped whitespace is still verbatim | Asserted |

**447 tests.** Four gates clean.


---

## Phase B2 — supply chain ✅

The objection this phase answers arrives on the first call and is not answerable with
*"it's open source"*: **is your tool safe to run?** Anyone can publish code, and stars
measure popularity rather than safety. §12's governing principle is not to earn trust but
to make trust unnecessary — every control makes the tool's behaviour constrained and
observable rather than believed.

So the test applied to each deliverable here was: *does a stranger have a command?* Not a
badge, not an assurance, a command that works in a clone they made themselves.

### The four layers, and the disagreement nothing was checking

Security scanners became a fourth dependency layer, `audit`, rather than four more lines
in `dev.in`. Semgrep alone pulls several dozen transitive packages, and burying them in
the file a contributor runs `pip install -r` against would undo the property that makes
*"read the dependency list in an afternoon"* true. Pinned and hashed like every other
layer: a scanner resolved at CI time is a statement about whatever was current that
morning, which is the class of claim this project refuses to make about anything else.

Adding a fourth chance to disagree surfaced that **nothing was checking the first three
agreed.** `score` is `generate` plus the ML stack, `dev` is `score` plus tooling — but
each lockfile is resolved independently, so nothing made `httpx` the same version in
`generate.txt` and `score.txt`. The dependency-boundary tests would have been exercising
one version and the shipped scorer another, and both would have passed. `check_pins.py`
gained a fifth property for it. Same reasoning as everywhere else in this build: the
failure was silent by construction, and silence is what makes it worth a gate rather than
a convention.

### The SBOM, and three deviations from the bullet

CycloneDX 1.6, one per layer, at `sbom/`. Three departures from what §17.2 asked for,
each because the obvious version would have produced a document that could not be
checked.

**Generated from the lockfiles, not from an installed environment.** The usual approach
scans a built venv. That describes whatever happened to be on the machine that ran the
scanner; the lockfile is what the repository *commits to*, and its hashes are the same
bytes `--require-hashes` enforces at install time. The SBOM and the installer now make
one claim rather than two.

**Committed, not generated in CI and attached to the release.** A reader gets it without
running anything — and, more usefully, it becomes drift-gateable. `gen_sbom.py --check` is
the fifth repository gate, the same ratchet `gen_schemas.py --check` applies to the
published contracts.

**No timestamp, and a derived serial number.** CycloneDX permits `metadata.timestamp` and
a random `serialNumber`. Either would change on every generation and make a committed SBOM
impossible to verify against the lockfile it claims to describe — the drift gate would be
theatre. The serial is `uuid5` over the lockfile's SHA-256, so regeneration is
byte-identical. Both absences are recorded *inside* each document, next to the third one
that matters: **licences are not listed**, because a lockfile carries none and reading
them off installed distributions would make the document depend on a machine again. That
is the F40 rule — an omitted field and an unknown value read identically — applied to
provenance rather than to a check result.

One SBOM per layer, not one per project, because a merged document listing torch would
misdescribe what a *target* installs, which is the only question they are asking. The
`dependencies` array carries the real resolution graph, parsed from uv's `# via` comments,
so a reviewer can see that torch arrives through `sentence-transformers` rather than
because we asked for it.

Validity is checked by something other than our own reading of the spec:
`scripts/validate_sbom.py` runs the schema published by the CycloneDX project. All four
documents validate strict 1.6.

### Signing: what it establishes, and what it does not

`release.yml` verifies the tag signature **before it builds anything**. A pipeline that
builds first has already spent its provenance on an unverified commit — the attestation
would be true and worthless. The public key is committed at
`.github/release-signing-key.asc` with its fingerprint published in `SECURITY.md`, so
verification needs no keyserver fetch; a keyserver fetch would mean the verification
trusted whatever the network returned that morning, which is the substitution the
signature exists to detect.

Four properties, and the point of each is *whose word it rests on*:

| Property | Rests on |
|---|---|
| GPG-signed tag and commit | A key committed to the repository, fingerprint published separately |
| SHA-256 checksums | Arithmetic |
| Cosign signature, keyless | Sigstore's public Rekor log — a signature made privately is visible as an absence |
| SLSA build provenance | GitHub's OIDC identity, which we cannot mint |

**`scripts/verify_release.sh` is the half that makes any of it worth doing.** Signing is
a claim like any other until someone checks it, and almost nobody checks a signature they
have to work out how to check. One command does all four, imports the key into a scratch
keyring rather than the reader's own trust store, and **refuses to continue past a failed
tag signature** rather than collecting three green ticks underneath it. `cosign
verify-blob` is called with `--certificate-identity`; without it, it accepts a signature
from any Sigstore identity, which is every identity.

**Cosign signs blobs, not images.** There is nothing published to sign. Image signing and
`trivy image` ship in the same change as the `generate`/`score` image split, not before
it — a workflow that scans an image we have not built is one that passes by having
nothing to do.

### Scanning, and the one thing that is not pinned

`pip-audit`, Bandit, Semgrep, Trivy. Weekly as well as on push, because the pins are
exact by design: nothing quietly resolves past a new advisory, so a scheduled scan is the
only thing that will find one. All four lockfiles audit clean as of 2026-08-03.

`pip-audit` runs **per layer** rather than once over everything. An advisory in
`generate` is a *target's* exposure — that is what they install on their own machine — and
one in `score` is ours. A single pass/fail would erase the distinction the whole
architecture exists to make.

Semgrep's **rules** are fetched from the public registry when the job runs, so a Semgrep
result is scoped to the rules published that day. The scanner version is pinned and
hashed like everything else; the ruleset is not. Written into `SECURITY.md` rather than
left implicit — it is the one unpinned thing in the pipeline, and pretending otherwise
would undercut everything that is pinned.

### Mutable pointers, found in two places

Every `uses:` in every workflow is a 40-character commit SHA with the tag kept as a
trailing comment. `actions/checkout@v7` runs whatever its owner moves that tag to — the
same substitution `--require-hashes` prevents one layer down. Pinning the whole dependency
tree to its bytes and then trusting six mutable references in CI would leave the claim
resting on the weakest link in it, and on the link nobody looks at.

The Dockerfile had the same defect and had said so: a `TODO(B2)` noting that
`FROM python:3.11-slim` is *"a pin in name only"*. It is now pinned by digest. That layer
carries the interpreter, the OS packages and the TLS store, so it was the largest unpinned
surface in the repository.

`tests/test_supply_chain.py` fails the build on an unpinned `uses:` or `FROM`, on a
pinned action with no version comment (the comment does not make the pin safer; it makes
the diff readable, which decides whether a reviewer notices the pin changing), on a
workflow that does not declare `contents: read`, and on write or `id-token: write`
permissions anywhere but the one release job — a second job with `id-token: write` can
mint a Sigstore identity as this repository, which is the entire basis of the provenance
claim.

### Egress, asserted a second way

`tests/test_dependency_boundary.py` proves the artefact route by *uninstalling httpx*: no
HTTP client is reachable, so no request can be made. CI now proves it the other way — the
client is installed and working, and the network itself is gone. The step runs
`plant → hash → score` under `unshare --map-root-user --net`, in an empty network
namespace where a socket call fails rather than resolving.

Both are worth having. The first says our code does not import a transport; the second
says it does not need one. A client asking *"what does this thing talk to while it runs"*
is asking the second question, and the answer should be a build step rather than a
paragraph. The script asserts it can *not* reach the network before it does anything, so
a runner where `unshare` silently did nothing fails loudly instead of reporting a
guarantee that was never tested.

### Found while building it

- **The claims gate only ever read `README.md`.** Appendix D's discipline applies to
  anything published, and Phase B2 added two documents whose entire subject is what the
  tool does and does not do. Widening the gate to `SECURITY.md`,
  `docs/threat-model.md` and `docs/responses-schema.md` failed on its first run:
  `responses-schema.md` asserted *"Nothing is sent anywhere"* with no scope attached — a
  stronger claim than the README was permitted to make, sitting in the file handed to
  third parties implementing the interchange format. The strongest claim in the
  repository was in the document under the least scrutiny.
- **The same paragraph claimed a container invocation that does not exist.** It described
  `score` running *"in a container with `--network=none`"* as the documented invocation.
  There is a Dockerfile, but no published image and no split; the honest replacement
  points at the namespace test and at `score` importing nothing from `transport/`.
- **The README said the mode split was pending.** It shipped in Phase B. A status table
  that lags the code is the same defect as a report that lags the run.
- **My own wording tripped the widened gate.** *"The SBOMs are deterministic"* was flagged
  for asserting determinism without scoping it to scoring. Rewording to *"regenerating
  from an unchanged lockfile produces a byte-identical document"* is the more precise
  claim anyway — which is generally what happens when a blunt rule fires on true text.

### Acceptance

| Claim | How it was checked |
|---|---|
| Every artefact of a release is signed and verifiable by a stranger with public tooling | `verify_release.sh` covers all four properties; `tests/test_supply_chain.py` asserts it checks everything `release.yml` produces, and with a certificate identity rather than any identity |
| SBOM generated and attached | Four CycloneDX 1.6 documents, committed and validated against the published schema; drift-gated; attached to every release |
| `pip-audit` clean | All four lockfiles, 2026-08-03, no known vulnerabilities |
| Public CI with linkable runs | `ci.yml`, `security.yml`, `release.yml`; weekly schedule; every action SHA-pinned |
| Hardened default invocation | **Partially met, and stated as such.** The README's primary invocation is the artefact route, where nothing of ours runs. §12.3's `docker run` is documented as the target, not as something runnable today |

**488 tests.** Five gates clean.

### Deliberately not done

- **Cosign-signed images, `trivy image`, and the `generate`/`score` image split.** Docker
  is last by instruction. Signing an image requires publishing one, so all three land in
  that change together.
- **A paid code audit.** §12.6: thousands of pounds, stale in months, invisible to anyone
  who has not already replied. Trigger is the first buyer who asks for one.
- **Pinning Semgrep's ruleset.** Vendoring the rules would pin them and freeze them; the
  registry version stays current. The trade is recorded in `SECURITY.md` rather than
  decided silently.
- **Signing the SBOMs separately from the release artefacts.** They are in `dist/`, so
  they carry the same cosign signature and the same provenance attestation as the wheel.

---

## Phase E — N-pass and variance ✅

Closes defect 3 in §19, which was marked **blocking** and is the only one whose damage
lands on *us* rather than on the target: without a variance pass, a system whose answers
vary between identical questions makes the **harness** look flaky. Two runs disagree, and
the reader's first thought is that the tool is unreliable rather than that the system is.

That is the whole phase. Scoring is deterministic and NF2 asserts it byte-for-byte. Target
systems typically are not. Naming the difference — before a vendor re-runs the battery and
discovers it themselves — is the difference between a finding and an excuse offered
afterwards.

### What was already done, and what was not

N-pass execution had been in place since Phase B: `--passes`, `pass_index` on every
record, and a refusal to accept two records for the same `(probe_id, pass_index)`. What
was missing was everything that reads them. So this phase was three things: the
classification, the check that reports it, and the two denominators.

### The classification, and a fourth §8.3 did not name

`identical` / `invariant_stable` / `divergent`, per §8.3. Only `divergent` is a finding —
**a generative system rewording an answer is not a defect**, and flagging ordinary
phrasing variation as failure is the fastest way to lose the rest of the report.

The fourth is `not_comparable`, and it exists because §8.3's three assume there is
something to compare. A probe asked once is not `identical`. Recording it as such would
let a single-pass run read as evidence of stability — the strongest claim in the document
resting on the least evidence for it. Same rule as F40 everywhere else: an absent
measurement and a clean one must not print the same.

It also covers a case worth stating: a probe eligible only for Tier 2 checks or for a
measurement has no invariant that *could* move. Where its answers were byte-identical
that is still `identical` — the fact is decidable from the text alone, so it is decided.
Where they differed, the honest record is *the wording changed; whether anything else did
is not established*.

### Two ordering decisions

**Outcomes are compared before text.** §8.3 lists its classifications as though equal
answers imply equal outcomes. They do not. Several Tier 1 checks read fields other than
the answer — leakage reads retrieved chunks, citation integrity reads document ids — so a
system can return a byte-identical answer over a different retrieval and change a verdict.
That is a divergence, and the one an output-level comparison would miss entirely. It is
classified as one, and the coincidence is printed rather than smoothed away: the report
says the answer text did not move and the outcome did.

**Tier 2 outcomes are excluded.** A cosine similarity of 0.851 on one pass and 0.849 on
the next crosses a line *we* set. Reporting that as the target's non-determinism would
attribute our own threshold to their system, which is the failure the tier split exists to
prevent. Measurements are excluded from the other direction — a check with no pass
condition has no outcome to diverge, and latency varies between passes by construction.

### `response_divergence` is registered, not bolted on

It is a `CheckSpec` like the other seventeen, with `cross_cutting=True`. Scoring runs in
two phases: the ordinary checks, then the cross-cutting ones with the others' results
handed to them. **It is the only check that can see another's verdict**, and a test
asserts the rest are handed an empty list — an evaluator able to read another's result is
one that can be written to agree with it, and the independence of the seventeen is what
makes a disagreement between passes mean anything.

Registered rather than appended after the loop because the registry is what puts a check's
tier, recipe, key and limit on the page. A finding assembled outside it would print
without them. The report is re-sorted into registry order afterwards, so a reader cannot
tell that variance ran last.

Its key is `open`. There is nothing to withhold: the expectation is that the system agrees
with itself, and a target who reads that in advance can satisfy it only by being
reproducible — which is exactly §3.6.1's test for what may be published.

Its denominator is the whole battery, declared centrally rather than in nineteen
`eligible_for` lists, so a probe added later cannot silently shrink it.

### The two denominators

§3.5 rule 4: *"60 eligible probes × 3 passes = 180 observations. Never collapse them."*
Every check now carries `failed_all_passes` and `failed_some_passes`, counting **probes**
where `failed` counts observations. A defect that reproduces and one that appears once are
different findings about different problems, and the second is usually the more valuable —
it is the one a vendor cannot reproduce on their own.

Printed only above one pass. At `passes: 1` every failure trivially failed all of its one
pass, and `failed_some_passes: 0` beside a single pass reads as *no non-determinism was
found* when none could have been. The fields stay in the JSON, because a consumer should
not have to tell an absent key from a nil count; the sentence is withheld from the page.

### Found while building it

- **The diff was taken over the first and last pass.** A probe that failed on pass 2 and
  recovered on pass 3 has identical first and last answers, so the report printed an
  **empty diff beside a finding** — the reader shown nothing and told it was evidence.
  The pair is now the first adjacent passes whose outcomes actually disagree, and the
  page names which two they were. Found by reading the rendered `report.md`, not by a
  test; the test came after.
- **The "not compared" message misdescribed its own cause.** It said *fewer than two
  scored passes*, when the usual cause is a probe eligible only for Tier 2 checks — three
  answers, nothing that could diverge. "4 probes were not compared" invites the reader to
  assume a transport failure. It now carries the reason.
- **`--passes` defaulted to 1 rather than to None**, so `--passes 1` against a config
  asking for 3 was indistinguishable from silence. A flag that cannot express its own
  default cannot override a config.

### Acceptance

| Claim | How it was checked |
|---|---|
| The `clean` profile at 3 passes produces zero divergence findings | A compliant battery reworded on every pass: zero findings, **and** a positive `invariant_stable` count — zero findings over answers that never varied would pass for the wrong reason |
| The `nondeterministic` profile produces a divergence finding | One outcome moved on one pass ⇒ exactly one finding, naming the check, carrying both texts and a diff |
| A single-pass run does not read as stable | `NOT_CAPTURED`, never `PASS`; §4 of the attestation says nothing was compared |
| Counts are split, not collapsed | A flaky probe and a stable one in the same run, asserted to land in different columns |

**520 tests.** Five gates clean.

### Deliberately not done

- **The live pathological target.** §14.1's HTTP mock with named profiles is Phase F2. The
  variance pass consumes a response file, so both profiles are expressed as response files
  here. The substance of the acceptance is met; the harness it was written against is not
  built, and F2 will re-run these two assertions against it.
- **Variance on Tier 2 scores.** Excluded by design, above. If it is ever wanted it is a
  *distribution* question — how far the score moved — not a pass/fail one, and it belongs
  beside the Tier 2 distributions rather than in a findings table.
- **Stability over time.** The check measures reproducibility across passes of one run.
  A system that answers identically three times this afternoon may answer differently
  after its next index rebuild, and the limit line on the check says so.

---

## Phase F — `validate` ✅

Closes defect 5 in §19. Wrong JSONPath is our own documented leading cause of false
positives, and a false positive in a delivered report is not recoverable in this niche —
we sell precision, and a finding retracted in front of a buyer takes the other seventeen
with it. Every condition in §7.1's table has the same shape: a setup problem that, left
uncaught, arrives at scoring time wearing the costume of a finding about somebody's
product.

`validate` sends three neutral throwaway queries, prints the raw response body beside
what the configured paths extracted from it, names what is wrong, and exits. Two minutes.

It is also the free pre-sale compatibility check: no corpus, no battery, no
authorisation, nothing disclosed in either direction. *Before you pay anything, run this
and confirm the harness can read your API* removes the "what if it doesn't work with our
stack" objection at zero cost.

### Non-leakage is structural, not careful

§7.1's warning is the sharpest constraint in the phase: `validate` prints raw response
bodies **to the target's terminal**, so a canary or an injection payload reaching this
mode is the product given away. The battery is what we sell; the harness is free.

The obvious implementation — take three probes from the battery and blank their
expectations — would have put an import edge from this package to `probes/`, leaving
nothing between a canary and their screen but our own care in maintaining it. There is no
such edge. The neutral probe set is a constant in `validate/neutral.py`, and the package
imports `config` and `transport` and nothing else of ours.

Asserted three ways, because each catches what the others miss:

| Assertion | Catches |
|---|---|
| The import graph is walked from `legal_rag_audit.validate` (AST, so imports inside functions count) — no edge to `probes`, `plants`, `corpus_loader`, `evaluators` or `score` | The refactor that reaches for a probe "just to reuse the shape" |
| Every value a real planting mints, checked against the neutral probes, the neutral document and its filename | A value hardcoded here that happens to collide with a minted one |
| The rendered output of a live run, checked against the same set | A value arriving through some path neither of the above covers |

### The projection needed a number the package is not allowed to look up

The run-length projection needs the battery size. Importing `probes/` to count it is the
one edge §7.1 forbids, so `BATTERY_PROBE_COUNT` is a plain integer in the `validate`
package — and a test compares it against `len(build_probes())` and fails the build when
they part company. Tests are not part of the package import graph, so the constant stays
honest without the package gaining the edge. `--probes probes.jsonl` counts lines in a
file the operator already holds, which is the exact count for an engagement and still not
an import.

### Every diagnosis carries §7.1's second column

That table is a list of conditions beside *what each one looks like in a report if nobody
caught it*, and the second column is the reason the mode exists. So it is stored on the
diagnosis rather than paraphrased into a log line. A 401 does not print "auth failed"; it
prints that it would otherwise read as an empty answer, and that half the battery treats
an empty answer as the system failing to produce something it should have — a wrong token
becoming a page of hallucination findings about a system that never saw a question.

Eleven codes: `auth_rejected`, `rate_limited`, `stream_never_terminated`,
`handshake_failed`, `upload_no_identifier`, `run_too_long`, `answer_not_extracted`,
`citations_not_extracted`, `answer_never_arrived`, `bad_status`, `unreachable`. The last
five are not in §7.1's table; they are the same class of problem and were cheap to name
once the shape existed.

### Blocking and advisory are different, and both are printed

`upload_no_identifier` and `run_too_long` do not stop the run. A target that issues no
document identifiers costs one Tier 1 check — citation integrity has no set to test
membership against, and the report will say `NOT_CAPTURED` rather than `PASS` (F40) — and
is otherwise a perfectly runnable engagement. A four-hour battery is not a defect in
anything; it is a fact about the engagement that is much cheaper to know now than at hour
three. Both are named in full, and neither is a reason to refuse to start.

**`validate` never exits 1.** Exit 1 means *ran, findings*. This mode judges no answer, so
it has no findings, and letting a setup check share an exit code with an audit result in
whatever CI reads it would be the exact conflation the mode exists to prevent. 0 or 2.

### Two things §7.1 asked for that needed a decision

**Order.** §7.1 says the raw body prints *alongside* the extraction. Which comes first is
not cosmetic: printed second, the body reads as supporting material for a conclusion
already stated; printed first, the conclusion is checkable against something the reader
saw with their own eyes. Same argument the evidence bundle makes for Tier 1 findings, at
a much smaller scale. Body first.

**Suggestions.** A confident wrong path is worse than no path — the operator sets it,
extraction starts returning *something*, and the something is a request id scored as the
system's answer. So candidates appear only where extraction came back empty, under a
heading saying they are guesses, with the value found at each one printed beside it. The
heuristics are deliberately dumb and their failure modes are stated in the module: longest
string wins, which breaks on a target that echoes the prompt; first array of objects in
document order, because the sources list sits near the answer and a longer array further
down is more likely to be retrieval debug output.

### Three defects that were all the same mistake

Each one sent the reader somewhere the problem was not.

**A 401 also reported the citations path.** The first version printed the auth diagnosis
and then, underneath it, `citations_not_extracted` — a note sending the operator to a
config key that was almost certainly correct, while the real cause sat above it. Three
empty answers and no citations is what an auth rejection *looks* like; it is not a second
problem. Both extraction diagnoses are now suppressed when a transport or status failure
was already named. Same rule the report itself runs on: an absent measurement and a failed
one must never print the same (F40). Found by running the thing and reading it.

**A refused websocket named the chat URL.** The generic *unreachable* branch reads the
chat endpoint, and a websocket that never opened is a problem with the *receive* address
— which had answered nothing and was not printed. The connection state is now observed
separately, and a connection that never opened is diagnosed before the generic branch and
against the right URL. It is also not `handshake_failed`: if the socket never opened,
`init_message` is not the thing to change.

**A `receive` endpoint polled over HTTP was reported as a stream.** An answer that never
arrived within the deadline got `stream_never_terminated`, whose remedy is to configure
`stop_payload_match` — a key that shape of config does not use. Polling now has its own
`answer_never_arrived`, and the rendering does not describe an answer arriving as "the
target's terminator".

### `nothing written` is now true rather than qualified

The CLI attaches a file handler to the logger for every mode, so a stranger running the
free pre-sale check would have found a `.legal_rag_audit.log` in the directory they ran it
from. Small, and exactly the kind of surprise that mode cannot afford. `validate` logs to
the terminal only. Qualifying the sentence in the README would have been the easier fix
and the worse one — the claim is short because the behaviour is.

### Acceptance

| Criterion | Result |
|---|---|
| The non-leakage test passes | Three ways: the import graph, the neutral material, and the rendered output of a live run |
| Each failure condition yields a named diagnosis, not a stack trace | One test per §7.1 row against a stub configured to misbehave in exactly that way, asserting on the diagnosis code rather than its prose |
| A well-behaved target produces nothing | Zero diagnoses, exit 0, and a closing line saying the run establishes that the harness can talk to the target and nothing about the target |

**582 tests.** Five gates clean. The jump is larger than the 44 tests in
`test_validate.py`: three of the repository-wide scans are parametrised over every file
in the package, so six new modules bring eighteen more assertions with them.

### Deliberately not done

- **No machine-readable output.** §7.1 is a mode a person reads over their own shoulder.
  A `--json` flag is easy to add and would need a schema, a version and a compatibility
  promise, which is three obligations for a use nobody has asked for.
- **No retry, no backoff.** On a 429 it says so and stops. A mode whose value is that it
  comes back fast should not be the thing that sits in a loop against someone's endpoint.
- **The neutral document is uploaded by default.** Checking whether the upload endpoint
  issues identifiers is not possible without sending something, and the check protects a
  Tier 1 evaluator. It is one small file, named so it is obvious in a document list, and
  `--skip-upload` suppresses it — the output then says the question went unanswered rather
  than quietly passing it.
