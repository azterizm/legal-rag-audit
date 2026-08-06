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
| **B** | `responses.jsonl` schema + offline `score` + probe/response spec + dependency split | 3 d | ✅ 2026-08-01 *(two Dockerfiles landed with J)* |
| **B2** | Hardened invocation, SBOM, signed tags + SLSA + cosign, CI scanning | 1 d | ✅ 2026-08-03 *(image signing and `trivy image` landed with J)* |
| **C** | Tier tagging + report v2 + manifest/hashing + GPG-signed releases | 2.5 d | ✅ 2026-08-02 *(signed releases are Phase B2)* |
| **D** | Seeded plant generation + collision guard; rewrite evaluators 4–14 | 4 d | ✅ 2026-08-03 |
| **E** | N-pass execution + variance reporting | 1 d | ✅ 2026-08-04 *(profiles are response files; the live mock target is F2)* |
| **F** | `validate` mode | 0.5 d | ✅ 2026-08-04 |
| **F2** | Pathological reference target + sensitivity/specificity gates | 1.5 d | ✅ 2026-08-04 |
| **G** | Existing-corpus mode + point-in-time pairs + licensed-content reproduction | 4–5 d | ✅ 2026-08-05 *(hero benchmark not run — it needs a decision about targets, §16)* |
| **H** | Reposition bundled corpus as demo; first domain corpus | 2.5 d | ✅ 2026-08-05 *(second corpus timed at 4m43s, but by an agent — a human timing is still owed)* |
| **I** | Authorisation controls + retention position | 0.5 d | ✅ 2026-08-06 |
| **J** | Container split, published and signed images, `trivy image`, the hardened invocation | — | ✅ 2026-08-06 *(last by instruction; closes the B and B2 remainders)* |
| **K** | `rag-probes-uk` corpus, config hardening, and the first run against a live commercial target | — | ✅ 2026-08-06 *(Vectara dry run; 4 defects found and fixed)* |
| **L** | Anchor set to six anchors and twelve readings, commercial anchors, NFC matching | — | ✅ 2026-08-06 |

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

---

## Phase F2 — the reference target ✅

Closes defect 11 in §19. The objection after *"is it safe to run against my system?"* is
*"how do I know your tool is right?"*, and until this phase the honest answer was that
the harness had never been run against a system whose defects were known in advance. Two
numbers now answer it, and §14.2 makes both publishable claims about our own instrument:
**sensitivity** — every registered check, given a target exhibiting the defect it looks
for, reports it — and **specificity** — a target behaving correctly produces no findings
at all.

The second is the one that costs money. A missed detection is a bug; a finding raised
against a system that did nothing wrong is a report we should never have sent, and in
this niche a retracted finding takes the other seventeen with it. So a false positive
blocks a release and a missed one does not.

### What the mock is not allowed to see

The whole phase turns on one decision. A reference target that answered by reading
`expectation.must_contain` would make the specificity gate a test that the scorer agrees
with itself — eighteen green rows establishing nothing. So the mock holds exactly what a
real target holds:

| It holds | It does not hold |
|---|---|
| The probe file — the questions, as handed over at §15.2 | The ground-truth manifest |
| The documents that arrived at `/upload` | The expectations, or any plant value as a value |

The invariants it answers with are **recovered from the uploaded bytes**. Each template
in `plants.templates` is prose with `@@plant-id@@` holes; the uploaded document is that
prose with the holes filled, so turning the template into a regex — literals escaped,
each hole a capture group — reads every planted value back out of what arrived. The
corpus, the questions and the answer key stay three separate artefacts that have to agree
for a run to come out clean.

The alignment does a second job nobody designed it for: it identifies *which* document
arrived. The retainer notice's base and revised bodies differ in prose as well as in the
fee, so the revision phase is observable to the target without being announced to it —
which is what makes `stale_index` a pathology this harness can express at all, and what
resolves `fresh-001` and `fresh-002` when a query alone cannot (they are the same
sentence asked either side of the revision).

A test asserts the mock's import set — `interchange.probe` and `plants.templates`, and
nothing else — so none of this can quietly stop being true.

### Every run is a full run

Corpus planted to disk, uploaded over HTTP, answered by a server that has only the probe
file and what arrived at `/upload`, captured through the transport client's JSONPaths,
written to `responses.jsonl`, scored offline against a key built from the same seed.
Eighteen profiles, twenty-one seconds, no network and no models.

This is what closes Phase E's recorded deviation. That phase's acceptance named the
`nondeterministic` and `clean` **mock profiles**, and both were expressed as response
files because this target did not exist yet. Both halves are now met against a live one:
three passes of `clean` produce zero divergent findings and a positive stable count, and
one moved outcome on one pass of `disamb-001` produces exactly one divergence, naming
`disambiguation` as the check that moved.

The distinction matters more than it sounds. A fixture proves the scorer reads what we
wrote into it. This proves the seams — upload, JSONPath extraction, capture notes,
document identifiers, the two-phase revision, the probe-text verification at scoring time
— and every one of those is a place a real engagement breaks that a fixture never touches.

### A pathology fails only what it claims

§14.2 does not ask for this and the number is worth much less without it. A mock that
answered every probe badly would light up sixteen rows and demonstrate nothing about
which evaluator caught which thing. So each profile's findings are asserted to be a
subset of what it declares, and the two unavoidable side effects are declared on the
profile rather than tolerated:

- `irrelevant_chunks` replaces the retrieval, and an answer cannot be entailed by chunks
  about something else — so the entailment check goes with it. The two Tier 2 checks read
  the same chunks; there is no way to move one without the other.
- `nondeterministic` moves a Tier 1 outcome on pass 2, and that pass is a genuine
  disambiguation failure. It has to be: variance is classified on Tier 1 outcomes, so a
  divergence that was not also a failure somewhere would be a rewording.

### One check cannot fail, and the gate accommodates it

§14.2 says *its evaluator reports FAIL*. `latency` cannot. It is a measurement (§8.2 #15)
— no pass condition, because any threshold would be ours rather than a standard — so a
gate demanding a FAIL from it would be unsatisfiable by design, and the tempting fix
(give it a threshold for the test) would put back the exact defect Phase C removed.

Detection for a measurement is the labelled paired reading instead: the contradictory
query taking materially longer than the baseline. Against the reference target the ratio
is **17.2 on `slow_regenerate` and 1.0 on `clean`**, and the clean case is asserted too —
a mechanism section telling a client their system silently regenerates answers, on a
target that does nothing of the sort, is a false positive in every sense that matters
commercially even though it never reaches the findings table.

The branch is taken off `spec.measurement` rather than off the check's name, so a second
measurement added later is covered without anyone remembering. §14.2 was amended to say
this rather than left describing something the code does not do.

### The two Tier 2 rows are opt-in, and the skip says so

They load checkpoints resolved by name rather than by digest — a gap
`instruments.weights_revision` already records — so the first run fetches several hundred
megabytes from a third party. Running that on every matrix entry of every push would mean
downloading unpinned weights three times a commit, and putting it in the release path
would mean a signed artefact depending on a third party returning the same bytes for a
mutable reference, which is the substitution `release.yml` exists to prevent.

So they sit behind `LEGAL_RAG_AUDIT_TIER2_GATE=1`, set in one CI job and nowhere else.
Where the flag is unset the rows skip and **name the two checks they did not verify**. A
gate that narrows itself quietly is the defect it exists to catch.

**They are unverified in this environment.** The scoring layer is not installed here, so
`unsupported_assertions` and `retrieval_relevance` were written against the same
reference target as the other fifteen and have not been observed to fire. The first CI
run with the flag set is what settles them.

### The matrix is a published artefact, and it is checked

[`docs/harness-verification.md`](docs/harness-verification.md) carries the eighteen
profiles, the two gates, and what neither number establishes: not that the battery is
complete, not that a real system fails the way a hand-written pathology does, not that
one seed's corpus is representative. Same discipline as `docs/responses-schema.md` — the
document is checked against the code on every run, because a published claim about our
own instrument that nobody re-derives is the kind we tell clients not to accept.

It was also added to the documents `check_readme_claims.py` covers, being the one whose
entire subject is how well our instrument works. That first run found nothing wrong with
the prose and one thing wrong with the gate: the determinism rule triggers on the
substring, so a table row named `nondeterministic` and a sentence about a target's
non-determinism both demanded a scoping clause about our scoring. NF2's whole point is
that the two differ. The rule now removes the negation before testing, exactly as the
sibling exfiltration rule already matched the assertion rather than the word — and a
paragraph that also asserts our own determinism still trips.

### Acceptance

| Criterion | Result |
|---|---|
| Both gates green | 42 tests. Sensitivity green for all 16 non-Tier-2 rows; specificity green at 3 passes |
| Wired as release blockers | Their own CI check on every push, and a step in `release.yml` before anything is signed |
| The matrix published in `docs/` | `docs/harness-verification.md`, gated against the code |

**626 tests, 610 passing under `-m "not slow"`.** Five gates clean.

Specificity is asserted more strictly than §14.2 words it. Zero findings is satisfied by
a run where every request failed, so the gate also asserts zero transport errors, no
unrecognised query, that citations, chunks and document identifiers were all captured,
that fifteen documents were accepted, and that every check is `PASS` or `NOT_ELIGIBLE` —
never `NOT_CAPTURED`, which is not a pass either.

### Deliberately not done

- **`serve_licensed_content` is absent.** It is §14.1's nineteenth row and it arrives in
  Phase G with the evaluator it exercises. A profile for a check that does not exist
  would be a matrix row that could never go green, which is worse than a row that says
  the check has not shipped.
- **The mock does not retrieve.** It looks each question up and answers correctly. A
  reference target with a real retriever would have its own defects, and a false failure
  on `clean` traceable to the mock's embedding model would be a release blocker raised by
  the instrument against itself. What the gate tests is the scorer, not the mock.
- **One seed.** Every profile runs against the same planted corpus, so a failure is about
  the profile rather than about which invariants that seed happened to mint. A sweep over
  seeds would be a different test — that the checks are robust to the corpus — and it
  belongs with the domain corpora in Phase H rather than here.

---

## Phase G — existing corpus and point-in-time ✅

Closes defect 4 in §19: `upload` was effectively required, which is a much larger access
ask than a chat probe and the one that turns a £500 engagement into a security review.
§9.1's second configuration now runs standalone — **no corpus, no upload endpoint, no
authorisation** — on ground truth that is a matter of public record.

The two configurations answer different objections and that is why the plan says to run
both. A planted run invites *"those are synthetic documents"*. This one invites nothing:
the questions are ones anyone could type into the product, and the answers are in the
statute book.

### The committed artefact is the anchor set, not the store

The phase brief reads *"ingestion: versioned snapshots, local store"*, which implies the
fetched text is the ground truth. It is not, and the inversion is the main design decision
here.

| Committed | Built by `ingest`, not committed |
|---|---|
| The anchor: a provision, a date, the phrase in force then, the URL | The snapshot: what the provision said when we looked, its digest, a bounded excerpt |
| Enough to build and score the battery, offline, with no network | Enough to prove the anchor is still right |

Scoring against fetched text was rejected for three reasons, and the third is the one that
settles it: every run would depend on a third party being up; a network fetch would sit
inside the one command that must work offline; and **a report's ground truth could change
between two runs of the same battery without anyone deciding that it should**. The whole
pre-commitment apparatus of §3.6 exists to stop exactly that.

`ingest --strict` is the refresh procedure and it inverts the usual risk. The one thing
the extractor cannot verify about itself is that its reading of CLML is right — a selector
matching nothing returns an empty string, and an empty string contains no phrase. So the
anchor's phrase is the test of the fetch rather than the other way round: a broken
extractor fails on every anchor at once instead of quietly agreeing with whatever it found.

**Footprint: 1.4 kB kept of 810 kB fetched** across four snapshots. §20.1 item 3 asked
whether versioned statute data is affordable to hold locally; the answer is that it is not
close, because the store keeps phrases rather than statutes.

### A phrase, not a provision

Matching a whole provision needs similarity, similarity needs a model, and a model would
move point-in-time correctness to Tier 2 — where the finding becomes contestable on our
threshold rather than on the law. That would give away the single strongest property this
check has: it is unarguably a **legal**-correctness question rather than an
engineering-taste one.

So an anchor carries a short phrase chosen under three rules, and every candidate that
failed one was left out rather than weakened:

1. **Discriminating** — in this version of the provision and no other.
2. **Not reachable by paraphrase of the other version.** This is the rule that rejects
   most candidates and it is the reason the commercial-contracts anchor §20.1 item 3 asks
   for is **absent**: the Late Payment of Commercial Debts (Interest) Act 1998 s.4 was
   restructured in 2015 around a defined term, *agreed payment day*, that a paraphrase of
   the pre-2015 wording — which lets the parties *agree a date for payment* — lands on
   without the system doing anything wrong. §14.2 makes a false positive a release
   blocker, so a phrase that can be reached innocently is not a phrase.
3. **Stable** — prefer two historic dates, because a closed validity range can never
   change again. `era-124` is that pattern on purpose and needs no maintenance ever;
   `era-108`'s second reading is the law as it stands, which is the more natural question
   and the one that can go stale. The two together are the argument for why `ingest`
   exists.

Both shipped anchors were verified against the primary source during the phase, and all
four readings came back clean.

### An answer carrying both versions passes

The decision that keeps this check off correct systems. An answer to *"as at 1 January
2011"* that says *"the period was then not less than one year; it is now not less than two
years"* is better than the one asked for, not worse. The finding is only ever **the
correct version is absent and the superseded one is there**.

`version_mismatch` ships as a **counter of `point_in_time` rather than a registered
check**. §10.5 lists it beside `unresolvable_citations` and `non_existent_authorities`,
which are both counters inside `citation_integrity`, and it reads the same way. It is
counted apart because an answer that names the provision correctly and then gives the
superseded text reads as authoritative and is wrong about the only thing that mattered —
which a reader triaging findings needs to know.

The **pair** is reported as a mechanism sentence and never as a second finding. One half
of a pair already fails on its own, so counting the pairing would count the same defect
twice in a report whose whole discipline is that denominators are visible.

### The licensed-content check is built so it cannot become an accusation

A finding here says a company's index holds material whose licence sits between them and a
publisher. §16.3 is blunt about the cost of getting it wrong: unlike a wrong grounding
call, this one alleges unlawful conduct by a named company. So the restraint is structural.

- **Identifiers only.** Westlaw and LEXIS citations and West Key Numbers — publisher-assigned
  strings that appear nowhere in the primary source. The editorial-prose class is not
  shipped at all: storing a publisher's headnotes in order to test whether somebody else
  has stored them would be the act under examination (§20.1 item 7).
- **Two classes are specified and not scored**, for the same reason citation counter (b)
  is not. Star pagination is indistinguishable from a page number in emphasis, and the
  signal marks are ordinary English words. The result says they were not scored.
- **Two of the three outcomes are not findings**, and both are tested. `external_fetch` —
  the marker cited to the publisher's own service — is the licensed thing working, and it
  passes. `unattributed` is `NOT_CAPTURED`: consistent with an index holding the licensed
  edition *and* with parametric recall, and this check cannot separate them, so it says so
  rather than picking the reading that produces a finding.

### Three deviations, all of them things the phase found

**`ground_truth.v3`.** `as_at_date`, `provision` and `paired_with` — none of which a v2
manifest can express — plus `corpus_mode`, which was added after the reference target's
existing-corpus run produced a manifest saying `corpus_mode: null`. `score` sees no config
and no corpus, and the absence of plants is true of a hand-authored planted battery as
well as an existing-corpus one, so the answer key now declares which of §9.1's two
configurations it is for. A report has to name that: a finding against documents we wrote
and a finding against the target's own index answer different objections.

**`endpoints.upload` became optional.** Found by the gate: the two new profiles failed
with a pydantic error, because the config schema required an upload endpoint even in the
mode whose entire purpose is not needing one. Requiring the key meant F25 could not be
configured without contradicting itself. The check that replaced it is behavioural — a run
with documents to send and nowhere to send them aborts naming the three ways out, because
*probe their index*, *assume they hold the corpus* and *declare somewhere to send it* mean
different things.

**`corpus.mode: existing` no longer reads a path.** It used to load a local directory and
upload it, which was planted mode wearing the other name — it still needed an upload
endpoint, so the one objection existing mode exists to defeat still applied.

### The gate went to 20/20, not 18/18

The phase brief expected `serve_licensed_content` to take the sensitivity gate from 17/17
to 18/18. It went to 20/20, because `point_in_time` is a registered check and the gate is
written against the register rather than against §8.2's list — so it refused to build
until that had a profile too. §14.1's table gains `answer_current_law` for it.

The reference target now runs **both batteries**, and the clean control runs on both. Each
battery reports the other's checks as `NOT_ELIGIBLE` rather than as passes: F40 applied at
the level of a configuration rather than a probe. A test asserts that between them the two
cover every Tier 1 check, because a check no battery exercises is one the register counts
and nothing tests.

### Acceptance

| Criterion | Result |
|---|---|
| A full run needs `chat` only — no `upload` endpoint | Met, and asserted on the config: the existing-corpus config declares no upload endpoint, so a run that tried could not have resolved a URL |
| `serve_licensed_content` produces an `in_index` finding | Met |
| A profile citing the publisher's own service produces `external_fetch` and no finding | Met |
| A marker with no retrieval evidence produces `NOT_CAPTURED` | Met |
| The aggregate result is publishable naming nobody | **Not met — the run has not happened.** See below |

**697 tests, all passing under `-m "not slow"`.** Five gates clean.

### Not done: the hero benchmark

§17.2 asks for a run across public configurations with the run sheet written first, and
preregistration is the cheapest credibility purchase available. The half that is not ours
to decide is **which configurations**. §16 makes that a question about authorisation
rather than capability — signing up for a product authorises use, not testing, and most
SaaS terms separately prohibit benchmarking. So the target list is a decision for a
person, and the preregistration document is worth writing once it exists rather than with
a blank where its subject goes.

Everything the benchmark needs is now built: the battery runs against `chat` alone, needs
no authorisation, and its findings are the rate-shaped class §16.4 identifies as
free-runnable.

### Deliberately not done

- **No commercial-contracts anchor.** §20.1 item 3 asks for employment *and* commercial
  anchors and only the first shipped. Naming the gap is better than filling it with a
  phrase that can be reached by paraphrase, which would fail correct systems on the check
  whose whole value is that its ground truth is not arguable.
- **No shingle hashing for editorial prose.** §8.2 #18 names it as the method where a paid
  engagement warrants matching headnotes without storing them. It stays out of the
  open-source core, which is what §20.1 item 7 decided.
- **The store is not committed and not gitignored into invisibility.** It is written where
  the operator asks and nowhere by default, because a store that appeared without being
  asked for would be a cache of Crown copyright material accumulating in someone's
  repository.

---

## Phase H — the corpus library ✅

**Shipped 2026-08-05.** §9.5's claim is that the fifth corpus in a practice area is half a
day because it is a template edit. The phase is about making that structurally true rather
than aspirational, and the shape of the answer is a split: **the structure is code and the
prose is data.**

### The spine, and why it is not an author's to change

`corpora/spine.py` declares the roles a corpus fills — which documents exist, what each is
*for*, which invariants it carries and of what kind, which tenant and namespace it belongs
to, which state it is in. Fifteen documents, twenty-nine roles. A corpus supplies prose for
them and nothing else.

That is what makes §9.5 item 3 enforceable. It says a contradiction pair, structural
nesting, a tenant split, an injection document and a zero-answer topic are **mandatory in
every domain corpus**, and the only form in which a rule like that means anything is one
where a corpus without them cannot load. `MANDATORY` maps each element to its document keys
and is checked at import; a corpus omitting one fails before a single request goes out.

It is also what removes the largest class of authoring mistake. The battery references
plants by id — `P("contra-v1")` — and those references are the same in every domain, so the
expectations, the eligibility lists and the whole check register are authored once. A
per-corpus copy of the expectations would let a domain corpus quietly start scoring against
a different plant from the one it planted.

Three things that were literals in the battery became references, because they are the
author's and not ours: `must_cite_any_of` was two filenames, `adjacency` identifiers were
the strings `"Statute Alpha"` and `"Statute Beta"`, and `planted_in` was `internal_memo.txt`.
An employment corpus has none of those. They resolve now through `D("agreement_v1", "cite")`
against the loaded corpus.

### Validation is the deliverable

The authoring loop is `plant --corpus <dir>`, run repeatedly. Every refusal names one thing
to write: the marker to put in a body, the plant with no recorded location, the unworded
probe, the document key the spine does not have, the remaining `TODO`. A validator that
only said *invalid* would move the discovery to the first run against a live target — where
a missing plant reads as a finding about somebody else's system, which is precisely what
NF9 forbids.

Two refusals are about something narrower and matter more than the rest:

- **A probe may not quote the answer it is scored on.** `{plant:<id>}` exists so a question
  can name a heading it could not otherwise retrieve on — you cannot ask about a support
  band without naming the band. An expected invariant in the question makes the answer an
  echo, and the check would pass a system that retrieved nothing.
- **The `out_of_corpus` lure must genuinely be absent.** §8.2 #6 scores parametric bleed by
  absence. A nominated phrase that turned out to be in a document would record a system
  quoting its own corpus as having answered from its weights — a false positive against a
  correct system, and §14.2 makes a false positive a release blocker. It was a module
  constant before this phase and was never checked against anything.

### What happened to the thirteen documents

§17.2 says *reposition the bundled 13-doc corpus*. Those thirteen were the v1 corpus whose
hand-written expectations Phase D replaced with seeded plants. By this phase nothing loaded
them: `corpus.path` had no consumer, `mode: existing` stopped reading a path in Phase G, and
the only thing keeping them alive was a packaging gate asserting they were in the wheel.

So the **name moved rather than the files**. `bundled-demo` now names the corpus the free
run actually uses — the fifteen planted documents, which carry the same nine roles §9.4's
composition table lists and, unlike the thirteen, carry ground truth. The thirteen were
retired; their content is in the history. Repositioning something that cannot generate a
report would have been repositioning a label.

The library lives at `src/legal_rag_audit/corpora/library/` rather than at the repository
root where §5.2 puts it. A directory outside the package cannot go in a wheel, and the
bundled demo has to run from a `pip install` — `tests/test_corpus_packaging.py` exists
because it once silently did not. Two locations would mean two lookup rules and a corpus
that resolves in a working tree and not from an install.

### Staleness, in the right register

§9.5 says corpora go stale because law moves, and that is the monitoring retainer's whole
basis. Stated carelessly it is also wrong. **No amendment can falsify a planted
invariant** — a correct answer is correct whatever Parliament does. What an amendment does
is make a corpus **unrepresentative**: the drafting these documents encode, and the
questions a reader would think to ask of them, are stated as at a date.

Both domain corpora say it in those words, and `docs/authoring-a-corpus.md` tells an author
to. Implying that a statutory amendment invalidates a synthetic document would be the exact
overreach this project is built to find in other people's reports. It is still a re-run
trigger, and it now reaches the attestation: the triggers are printed under *Limits*, so a
report says when it stops being current rather than leaving that in a file nobody opens.

### What ships

| Corpus | Domain | Triggers |
|---|---|---|
| `bundled-demo` | none — synthetic | **none, and that is the answer**: it states no legal position, so nothing can reach it |
| `commercial-contracts` | supply, services, procurement (E&W) | UCTA 1977, Late Payment 1998, Procurement Act 2023 |
| `employment` | contracts, policies, tribunal work (E&W) | ERA 1996, WTR 1998, Equality Act 2010 |

Plus `TEMPLATE/`, which is generated by `scripts/new_corpus.py` and committed. A test
asserts the committed skeleton is byte-identical to what the generator produces, so adding
a role to the spine breaks the build until the skeleton is regenerated. A drifted skeleton
would scaffold a corpus missing the new document, and the author would discover it from a
validation error rather than from the template — exactly the discovery this phase moves
earlier.

`ground_truth.v4` carries the corpus name, version and digest. A v3 manifest names a seed,
and the same seed against two corpora mints the same values into different documents and
asks different questions; without the corpus reference two reports could not be compared and
neither could be reproduced by anyone who did not already know which corpus was used.

**Verified:** the published demo seed produces a corpus byte-for-byte identical to the one
it produced before the refactor. That was checked against a worktree at the previous commit
rather than asserted.

### The acceptance, and the part of it that is not met

> *authoring a second domain corpus from the template is timed and comes in under half a
> day.*

The employment corpus was scaffolded and authored in **4 minutes 43 seconds** of wall clock,
in a single pass, with no structural rework. That number is not the one the acceptance
asks for: an agent writing prose at machine speed is not evidence about a human's half day,
and reporting it as though it were would be the kind of measurement claim §3.5 exists to
prevent.

What the run does establish is the thing the half-day claim actually rests on: **no design
work remained.** The scaffold arrived with every document, every slot, every location line
and every probe placed. What an author adds is prose, question wording, and the two
judgment calls the loader cannot make — what would date the corpus, and which authority a
model reliably knows that no document here mentions. A human timing is owed and is recorded
as outstanding.

**754 tests, all passing — the whole suite, not `-m "not slow"`.** Six gates clean (`check_readme_claims.py`
now covers `docs/authoring-a-corpus.md`). Sensitivity and specificity still 20/20.

### Deliberately not done

- **No third domain corpus.** Two is what §9.5 asks for and what makes the template claim
  checkable; a third would be repetition rather than evidence.
- **The reference target still runs against `bundled-demo` alone.** §14 verifies the
  *harness*, and running the same nineteen probes against a second set of prose would
  re-verify the mock rather than the instrument. What is tested per corpus is that every
  shipped one loads, plants, builds a battery, and satisfies the two absence properties.
- **`corpus.library` is not yet in the §6.1 config v2 migration.** It is a new optional key
  with a null default, so an existing config still loads; the rename backlog
  (`display_thresholds`, `battery.probes_path`, `battery.seed`) is unchanged.

### Two defects the phase found, both older than it

Running `pytest -m "slow"` — which Phases E through G did not — turned up two things that
had nothing to do with corpora.

**Four assertions had been stale since Phase G.** `checks_registered == 18`, written when
the register held eighteen, in tests marked `slow`. Phase G took the register to twenty and
these kept passing under `-m "not slow"`, which is the mode every phase since E has verified
in. CI runs the full suite, so **`2d7495a` would have been red there**. All four now compare
against `len(REGISTRY)`: a literal in a slow test is a claim nobody re-reads, and the claim
in question is *the torch-free install sees every check* — exactly the kind that has to hold
by construction rather than by having been true once.

**A stale `build/` directory could put deleted files into a wheel.** The packaging test
built with `python -m build --wheel`, which reuses `./build/lib` in place; the wheel it
produced still carried `ground_truth.v2` and `v3` schemas that no longer exist in the source
tree. Dropping `--wheel` builds an sdist first and the wheel from that, in a clean tree,
which is both what a release does and the only way a test asserting *the artefact is what
ships* can mean anything. The published artefacts were never affected — CI checks out clean —
but the test that exists to catch exactly this was building the wrong thing.

The habit that hid both: verifying a phase with `-m "not slow"` and reporting the number.
The full suite is 754 tests and takes eighty seconds.

---

## Phase I — the boundary, enforced ✅

**Shipped 2026-08-06.** §16 tells a reader in prose that signing up for a product
authorises use and not testing. This phase is where that stops being a promise about our
conduct and becomes a property of the software: `generate` refuses to send a single
request until the condition is satisfied, and the refusal names every reason.

### Two triggers, not one

§13 classes probe families by authorisation requirement. Implementing only that would have
been wrong, because it misses the act that actually needs consent most obviously.

**The families a battery asks.** `authorisation.py` classes *every* family both batteries
ask — not just §13's five — as data, each with a one-line account of what running it does
to somebody else's system. Written for the person reading an abort message at nine at
night: *"tests injection resistance"* explains nothing, and *"plants an instruction inside
a document and tests whether the retriever obeys it"* explains everything. An unrecognised
family is treated as needing authorisation, because the safe reading of *nobody has
decided* is not *this is ordinary use*; a test asserts every family in either battery is
classified, so the fail-closed default stays a backstop rather than becoming the mechanism.

**Whether it uploads.** §16.1 puts *uploading adversarial documents* in the column headed
never on a self-signed-up account, and the planted corpus carries an injection payload by
construction. So the upload needs consent whatever families ride on it — and the abort
message names the way out, because the configuration that needs no upload and no
authorisation is the thing an operator most needs to be told about at that moment.

`require()` collects every reason rather than the first. An operator who fixes one and
re-runs into the next has been told the truth twice instead of once.

### Where the gate is, and where it is not

**In `generate`, before the first request.** Asserted against an endpoint with nothing
listening on it: a run that got as far as sending would fail with a connection error and
write a response file, and this one exits 2 with a diagnosis and writes nothing. That is
the difference between a control and a log entry.

**Not in `score`.** The first implementation refused to score a response file that
recorded an authorised-testing battery with no block, and it was wrong twice over. By the
time a response file exists the requests have been sent, and refusing to read it does not
un-send them — it only means nobody gets a report about what happened. It also breaks the
artefact route (§5.1.1), where a file produced by the target's own harness against their
own system legitimately carries no block, and that route is the whole low-friction
premise. So `score` records the absence under *Limits*, and **no block and none needed**
prints differently from **no block and one was needed** — opposite facts about a run, and
F40 says they may never read the same.

### Production needs two acts

`environment: production` in the config is refused without
`--i-have-written-authorisation-for-production` on the command line. A config is copied
between runs; a command line is typed for one. The flag alone authorises nothing, and
both directions are tested.

### What the report carries, and what it does not claim

The block is verbatim in the run manifest and in its own attestation section. Printed
beside it, in the same block: *it records what the operator declared; it is not itself
evidence that the declaration was true.* A determined operator can type a name into a YAML
file, and a page that let the block imply otherwise would be doing the thing this project
measures in other people's reports.

**No expiry is enforced.** The manifest records how old the authorisation was on the day of
the run and leaves the reader to decide whether a scope from two years ago still covers it.
Any number we chose would be the `0.85` mistake again (F24) — ours, presented as a
standard.

### The reference target is not exempt

Its planted battery now declares an authorisation block naming the mock it runs against.
That it probes a target we wrote does not change which families it asks, and a gate our own
harness routed around would be a gate that holds until it matters. The existing-corpus
battery deliberately declares none — that asymmetry is the assertion, and it is the same
one already made about `endpoints.upload`.

### The two free paths stayed free

`validate` needs no authorisation: three neutral throwaway probes, in a package with no
import path to the battery, carrying no family for the gate to classify. The
existing-corpus battery needs none either: it uploads nothing and every family on it is
ordinary use. Neither is an exemption written into the gate — both fall out of the rule,
and a gate that had caught either would have been written to the wrong one.

### Recorded deviations

Three, all above: `responses.v3` carries the block in the capture notes because `score`
sees no config; `score` records rather than refuses; no expiry is enforced.

**781 tests, the whole suite.** Seven gates clean —
`check_readme_claims.py` now covers `docs/authorisation-and-retention.md`. Sensitivity and
specificity still 20/20, now with the reference target declaring its own consent.

### Still outstanding after this phase

- **`/trust` and the engagement terms.** §15.7's retention position is drafted in
  `docs/authorisation-and-retention.md`. Both destinations are outside this repository.
- **Rate limits are defaults, not a control.** §13 rule 5 says they are set so an ordinary
  run is indistinguishable from a user rather than a scanner. They are, and nothing
  enforces that a config cannot raise them. That is correct for a client running against
  their own system and would be wrong for a free-tier run against somebody else's; the
  distinction is not currently in the code.

---

## Phase J — the container, last by instruction ✅ 2026-08-06

Not a phase in §17.1. Docker was deferred from Phase B and again from B2, at your
instruction, and it carried the remainders of both: the `generate`/`score` image split,
image signing, `trivy image`, and §12.3's hardened `docker run`. They belong together
because each of the last three needs a published image to be about.

**Docker was available on this machine this time.** Every claim below was run, not
written. The previous Dockerfile changes went in untested and said so in the progress
record; that note can now come down.

### Two images, and what makes the boundary real

`Dockerfile.generate` installs `requirements/generate.txt` — five pure-Python libraries —
and `Dockerfile.score` installs `requirements/score.txt`, which is the same set plus the
ML stack. 279 MB against roughly two gigabytes, and the difference is the entire argument
of §5.3.

The thing worth having is not the split; it is what now tests it. `tests/test_container.py`
imports `torch`, `transformers`, `sentence_transformers` and `numpy` **inside the built
image** and requires each to fail. `test_dependency_pinning.py` asserts torch is absent
from a text file; `test_dependency_boundary.py` asserts it about a virtualenv pip
resolved. Neither is the artefact a client is handed. A security reviewer is asking what
lands on their machine, and now something checks that.

Both are multi-stage. What ships is a virtualenv and an interpreter — no pip, no build
backend, no source tree. That is a shorter file list for a human reading the image and a
shorter package inventory for `trivy image`, where every entry is one somebody needs a
reason for.

**Two pinning decisions inside the build.** `--no-build-isolation`, because PEP 517
isolation *downloads* setuptools at build time, and a build that fetches its own backend
over the network is exactly the unpinned link every other line in the file removes;
without isolation the backend is the setuptools inside the base image, fixed by the same
digest as the interpreter. And both files carry the **same** base digest, asserted by a
test: two base images would mean two OS package sets and a `trivy image` finding against
one that silently does not apply to the other.

### The flag that did not exist

§12.3 and the README both printed `--network=host-allowlist-only`. **There is no such
Docker network.** It was standing in for *a network the reader has configured to permit
one destination*, and a reader who pasted it would have got an error — from which the
reasonable inference is that the rest of the page is decorative too.

**Docker cannot express a per-container host allowlist.** It has no flag for it. What it
can express is *no external route at all*:

```
docker network create --internal audit-net
```

Verified in both directions, and the second direction is the point: a container on
`audit-net` gets `Network is unreachable` connecting to `1.1.1.1:443`, and the *same
image* on the default bridge connects. A denial test that would also pass on a broken
image establishes nothing. The allowlist is then a forward proxy of theirs on that network
and on one that reaches their endpoint — which is the logging proxy §12.3's table already
wanted, and their connection log rather than our claim.

`docs/hardened-run.md` — named in §5.2's layout since the start and empty until now —
carries the three invocations, what each flag answers, and the paragraph admitting the
substitution rather than quietly correcting it. `tests/test_container.py` now fails if any
published document prints a `--network=` value that is neither `none` nor a network the
same document tells the reader how to create.

`--user 65534:65534` also became `--user "$(id -u):$(id -g)"`. A fixed uid that does not
own the host output directory fails on the first run, and the fix people reach for is
`chmod 777`. A hardened invocation that makes somebody loosen permissions elsewhere has
moved the problem rather than solved it.

### Two defects the container found in the CLI

Both were NF9 failures that only a read-only filesystem would surface.

**The log file aborted the run.** `_configure_logging` opened `.legal_rag_audit.log` in
the working directory unconditionally. Under `--read-only` the first thing a target saw
was a traceback out of `logging`'s internals — loud, and not a diagnosis. The log is now
best-effort and **its absence is announced**: a run with no log and a run whose log was
written must not print the same thing (F40). It is a convenience; the evidence is the
report and the manifest.

**A forgotten mount was fifteen frames of `pathlib`.** Now one handler at the top of
`main()` turns an `OSError` into a named path and a sentence saying this is a path
problem, not a finding, and nothing was scored. It is deliberately at the top rather than
per command — every command that writes has the same failure, and the one that got
forgotten would be the one a stranger hit. It fires **only when the error carries a
filename**: a socket error is an `OSError` too, and calling a refused connection a path
problem would be a worse diagnosis than the traceback it replaced.

### No `VOLUME`, on purpose

Declaring `VOLUME ["/out"]` — which the old Dockerfile did — makes Docker create an
anonymous volume when nobody mounted one. The run succeeds, writes the report into a
directory that dies with the container, and reports nothing wrong. Without the
declaration the write hits the read-only rootfs and aborts naming the path. NF9 applied
to the container rather than to the code, and a test asserts neither file declares one.

### Publishing, signing, scanning

`release.yml` builds both images from the already-verified tag, pushes to `ghcr.io`,
attests SLSA provenance per image, and cosign-signs **by digest**. `cosign sign
image:v0.2.0` would sign whatever that tag resolves to at that moment — a signature over a
name, and names can be moved afterwards by anyone with registry write access. `latest` is
not published at all.

The tag-to-digest mapping goes into a file called `IMAGES`, which is then checksummed,
cosign-signed and attested alongside the wheel. Without it the mapping lives only in a
registry run by the same people who published the release, and *"run this digest"* is an
instruction a reader cannot check against anything. `verify_release.sh` gained a fifth
section that reads `IMAGES` **after** verifying it, and fails a reference that carries no
digest rather than verifying a tag.

`trivy image` runs per image with `fail-fast: false`, on the reasoning that already made
`pip-audit` per layer: an advisory in the generate image is a *target's* exposure, on a
machine we do not own; one in the score image is ours. Each run also uploads a CycloneDX
SBOM **of the image** — the one inventory `gen_sbom.py` cannot produce, because it builds
from the lockfiles, correctly, and lockfiles describe no Debian package. The base digest
was bumped in the same change, since introducing an image scan on a months-old base is
introducing a red gate.

### A defect the image made visible

Building the score image is what surfaced it: **18 of the score lockfile's 68 packages
are CUDA.** `nvidia-cublas`, `nvidia-cudnn-cu13`, `nccl`, `cusparselt`, `nvshmem`,
`triton` — all gated on `sys_platform == 'linux'`, all arriving behind `torch`, on a
scoring path §5.3 describes as CPU and §5.4 as CPU-only, which never touches a GPU.
`nvidia-cublas` alone is a 543 MB wheel.

This is a **lockfile** property, not a container one. Every Linux `pip install -r
requirements/score.txt` has carried it since the lockfiles were written, and neither
`check_pins.py` nor `pip-audit` nor the SBOM would ever have said so — they all check
that the set is pinned and consistent, and this set is both. The image is what made it
visible, because the cost of installing something shows up in a layer.

**Not fixed here, deliberately.** The fix is a CPU wheel index in
`requirements/score.in` and a re-lock, which moves all four SBOMs, `check_pins.py` and
what every Linux user gets from a plain `pip install`. That is a dependency decision with
its own question attached — whether the CPU wheel still resolves universally across macOS
arm64 and Linux x86_64, because a lockfile that silently disagrees per platform is worse
than a large image. Slipping it into a container change would be the wrong place for it.
Recorded as defect 13 and open decision §20.1 #9.

### Model weights are mounted, not baked

The score image ships without checkpoints and with `HF_HUB_OFFLINE=1`, so a cache miss
**fails at load rather than fetching**. Scoring that claimed to run offline while quietly
reaching a model hub on a cache miss would be the one place the local-path claim failed,
in the one place nobody looks.

`--build-arg BAKE_MODELS=1` exists and is not the default, and the reason is not image
size. The two checkpoints resolve by *name*, with no revision pinned — a recorded manifest
gap, not a solved problem. Baking makes the image the pin: whatever was published that day
is what that digest contains forever. For a signed release that is an improvement and it
is also a signature over bytes nobody reviewed, so it is an explicit act.

### Acceptance

| Claim | How it was checked |
|---|---|
| NF3 — two images, `generate` slim, both non-root | **Generate: fully verified.** Built at 279 MB, `id` reports uid 65532, and `torch`, `transformers`, `sentence_transformers` and `numpy` each fail to import in it. **Score: built to the point that made defect 13 visible, then left downloading.** The CUDA wheels are gigabytes and this machine's link is not; `security.yml` builds it on every push with a layer cache, and `LEGAL_RAG_AUDIT_DOCKER_SCORE=1` runs the local test. The far side of the boundary is asserted by a test that has not yet had a chance to run here, and that is the weaker claim |
| §12.3's invocation is runnable | Every flag run: `--read-only --cap-drop=ALL --security-opt no-new-privileges --user --tmpfs`, with `plant`, `hash` and the artefact route |
| §5.1.1 in a container | `plant → hash → their harness → score` end to end inside the **generate** image under `--network=none`, pre-commitment verified, 19 of 19 probes put verbatim |
| Egress denial is enforced by the network | `--internal` network: `Network is unreachable`. Default bridge, same image: connects |
| Images signed and verifiable by a stranger | `verify_release.sh` section 5 — cosign against a certificate identity plus `gh attestation verify`, both by digest. Not yet exercised against a real tag: no release has been cut since the workflow changed |
| `trivy image` | In `security.yml`, per image, `fail-fast: false`, plus an image SBOM artefact. Not yet run — it runs on push |

**814 tests, the whole suite, 4 skipped.** Seven gates clean;
`check_readme_claims.py` now covers eight documents.

### Recorded deviations

- **`--network=host-allowlist-only` and `--user 65534:65534` were both changed**, with the
  reasons written into §12.3 rather than silently corrected. The first does not exist; the
  second produces a permission error whose usual fix is worse than the problem.
- **Published images are `linux/amd64` only.** An arm64 image is one `docker build` away
  and that is how everything above was checked, on Apple Silicon. Publishing an emulated
  build nobody ran, to save a reader one command, is shipping an untested artefact.
- **`--retries 10 --timeout 120` on the score layer's pip install.** It is two gigabytes,
  and pip's 15-second default turned a slow mirror into a failed build — twice, here. A
  build that fails on network weather teaches people to re-run until it passes, which is
  the habit that makes a real failure invisible.

### Still outstanding after this phase

- **Nothing has been published.** The workflow, the signing and the verifier are written
  and unit-checked; none of it has run against a real tag, because no tag has been cut.
  The first release is what turns section 5 of `verify_release.sh` from tested code into
  a verified claim.
- **The score image has not been built to completion on this machine.** Its lockfile
  pulls roughly three gigabytes of CUDA (defect 13) over a 1.5 MB/s link. What that
  build did establish is defect 13 itself. The image is built on every push in
  `security.yml`, and `LEGAL_RAG_AUDIT_DOCKER_SCORE=1` runs the local test — but until
  one of those goes green, "the ML stack is importable in the score image" is asserted
  by a test rather than by a run, and the two are not the same thing. The generate
  image — the one that matters to a target — is built and exercised on every slow run.
- **Defect 13, the CUDA stack in the score layer.** Recorded, not fixed: the fix is a
  lockfile decision (§20.1 #9), and it is the thing to settle before a score image is
  published rather than before this phase closes.

---

## Phase K — the first run against something we did not write

Every phase before this one was checked against `tests/mock_target` and the reference
target. Both are ours. Phase K pointed the tool at Vectara — a commercial retrieval
platform, first-party account — and the value of it was almost entirely in what broke.

**Four defects, all found by the run and none by the test suite.** That is the phase in one
sentence, and it is the argument for doing this again before every release rather than
after.

### What was built

**`corpora/library/rag-probes-uk/`** — a fourteen-document corpus in which every
instrument is invented. Shapes are adapted from the published battery at
[azterizm/rag-security-probes](https://github.com/azterizm/rag-security-probes): the
colliding section 42s of the Ravensbourne and Blackmere Acts, the Project Titan indemnity
schedule, the restricted transaction file, the CV injection payload. The **values** are
not adapted — they are minted from `corpus.seed` like every other corpus here, which is
the whole reason for porting shapes rather than pointing at the repository. That battery
is public, and its own README says publication contaminates it: *"A passing result is a
self-assessment, not audit evidence."* A seeded run of the same shapes is not answerable
from having read it.

`staleness_triggers: []`, and this is the corpus that setting was written for. Parliament
cannot amend the Blackmere Act. It is the only *working* corpus in the library with no
re-run trigger, which also makes it the one to reach for when the target is not a legal
product at all — a platform with no legal index can still be measured, because every
answer has to come from documents the operator put there.

Two upstream families did not survive the port, and the corpus README names them rather
than leaving the count to be noticed: **lost-in-the-middle** (the nesting is there, the
burial distance is not — fourteen short documents cannot bury anything) and **negation
blindness** (genuinely missing, genuinely Tier 1, and the obvious twentieth check).
Both need a spine role, a battery probe and an evaluator, and none of that was in scope.

### Defect 14 — a config could ask for something the run did not do

`config.yaml` carried a `tests:` block of seventeen check toggles. Pydantic's default is
to ignore unknown keys, so all seventeen were dropped on the floor. A config could say
`injection_resistance: true`, run a battery with no injection probe, and produce a report
mentioning neither the request nor its refusal.

That is the failure this tool exists to find in other people's systems, sitting in our own
config loader. Every model in `config.py` now sets `extra="forbid"`, and `tests:` gets a
named diagnosis pointing at `eligible_for` — which is the honest answer to where the
setting went: check eligibility is sealed into the battery and covered by the handover
hash, so a toggle set afterwards could not have been part of what was pre-committed.

### Defect 15 — an unset credential arrived as a finding

`TargetClient._build_auth_headers` warned on a missing token and substituted
`"DUMMY_TOKEN"`. Every request would then be rejected, and rejections are recorded as
responses — so an unset environment variable reached the report as a target that answered
wrongly. An absent measurement and a failed one must never print the same (F40); this one
printed worse. It now raises `AuthTokenMissing` before anything is sent.

### Defect 16 — the harness assumed upload was upsert

`_revision_phase` replaced a document by uploading it again. Vectara's `upload_file` is
create-only and answers **409**; `DELETE` then upload answers 204 and 201. Verified
directly against the API rather than inferred from the traceback.

This is not a Vectara quirk. `index_freshness` is mandatory in the spine and was
**unrunnable against any create-only ingest API**, and nothing in the config could say
"remove this first".

The fix is `endpoints.delete`, and it is the only destructive call this tool has, so the
fence around it is larger than the feature. Absent by default. Used in one place, the
revision phase. Only against identifiers *this run uploaded* — and by the identifier the
**target** issued, not ours, because `integration_fee_notice` is Vectara's
`integration_fee_notice.txt` and deleting the wrong string succeeds silently on any API
that treats a miss as a no-op. `method` defaults to DELETE here and POST everywhere else,
distinguished through `model_fields_set` so a deliberate POST-based delete API still
works. `tests/test_generate_delete.py` is eight tests, and six of them are about the
delete *not* happening.

### Defect 17 — a partial failure discarded complete evidence

The 409 aborted the whole run and wrote no response file, losing eighteen answered probes.
The abort reasoned that every check depends on the target holding the corpus — true of the
base upload, wrong here: the base corpus *was* uploaded and the first-phase probes *had*
returned. A failed revision upload is now the third loud-skip path beside the two that
already existed, and index freshness reports `NOT_CAPTURED`.

Base-upload failures still abort, and the asymmetry is the point. Without the base corpus
every check is scored against documents the target may not hold — not partial evidence but
wrong evidence.

### The run

`plant → hash → validate → generate → score`, end to end, against `api.vectara.io`.

| | |
|---|---|
| Corpus | `rag-probes-uk` v1, seed `vectara-dryrun-2026-08`, 29 plants, 0 regenerations |
| Uploaded | 14 documents, then 1 replacement after a delete |
| Probes | 19 asked, 16 answered, 3 transport errors (Vectara 500s) |
| Checks | 20 registered — 10 passed, 4 findings, 2 not eligible, 4 not captured |
| Pre-commitment | verified against the handover sealed before the target saw anything |

`validate` earned its place before any of this: it found that `citations_field` defaulted
to `response.sources` while Vectara returns `search_results`, so every citation check would
have scored a system that cites nothing. That would have been a finding about our JSONPath
printed as a finding about the target.

**The findings are not claims about Vectara, and the report should not be read as one.**
Everything went into a single corpus with no tenant separation and no namespace scoping,
and `multi_tenant` was not configured — so `cross_tenant_leakage` failing is a property of
how the run was set up, not of the product. `routing_contamination` passing is luck for the
same reason. What the run establishes is that the pipeline works against a real commercial
endpoint and that the four defects above are fixed.

### Still outstanding after this phase

- **The three Vectara 500s are unexplained.** `inj-001`, `conf-001` and `fresh-002` each
  returned a server error. They are correctly held as `NOT_CAPTURED` rather than findings,
  which is the behaviour working, but nobody has established *why* — and one of the three
  is the injection probe, which is the one where a server error and a refusal look alike.
- **Tier 2 did not run.** Scored with `--skip-tier2`, so `unsupported_assertions` and
  `retrieval_relevance` are recorded as not run. The three model-backed checks have still
  never been exercised against a live target.
- **One pass.** `response_divergence` is `NOT_CAPTURED`; reproducibility was not measured.
- **`rag-probes-uk` is exempted from the staleness assertion by name**, in
  `tests/test_corpora.py`, because nothing in the manifest schema expresses "states no
  legal position". A third synthetic corpus is the point at which that becomes a field.

---

## Phase L — the denominator

The existing-corpus battery worked from the day it shipped and was too small to publish a
number from. Two anchors, four point-in-time probes. *"X of 4"* is not a figure that
survives a sceptical reader, and it was the binding constraint on §16.7's hero claim —
not the target list, which is a decision, but this, which is work.

**Six anchors now, twelve readings.** Every one verified against `legislation.gov.uk`
live, not asserted:

```
ok  era-108 @ 2011-01-01  'not less than one year'     ok  era-186 @ 2014-01-01  '£450'
ok  era-108 @ current     'not less than two years'    ok  era-186 @ 2019-01-01  '£508'
ok  era-124 @ 2012-01-01  '£68,400'                    ok  ca-382  @ 2014-01-01  '£6.5'
ok  era-124 @ 2014-01-01  '£74,200'                    ok  ca-382  @ 2019-01-01  '£10.2'
ok  era-227 @ 2014-06-01  '£464'                       ok  ca-465  @ 2014-01-01  '£25.9'
ok  era-227 @ 2020-06-01  '£538'                       ok  ca-465  @ 2019-01-01  '£36'
```

The battery goes from **6 probes to 14**. Point-in-time goes from 4 to 12 — a threefold
denominator on the check the hero number is about.

### §20.1 item 3, answered

Employment anchors shipped in Phase G and commercial ones did not, because the obvious
candidate — Late Payment of Commercial Debts (Interest) Act 1998 s.4 — has no phrase that
survives rule 2. The Companies Act 2006 accounting thresholds do, and by construction:
every version states a different set of figures, so rule 1 holds automatically and a
paraphrase of one threshold cannot produce another threshold's number.

### A fourth rule, learned by rejecting things

Anchors were chosen **from the primary source**, by fetching each provision at several
dates and reading what actually differs. A figure remembered wrongly becomes a false
positive against a correct system, and that is the one output this tool must never
produce. Three candidates were rejected, and the reasons are now in `anchors.py` beside
the three original rules:

- **ERA 1996 s.31** (guarantee payment daily limit), whose readings are `£24.20` and
  `£28.00`. A system answering *£28* is right and would have been recorded as returning
  the superseded version. **Trailing zeros are not a phrase**, and that is the fourth
  rule: the figure must have one written form.
- **Insolvency Act 1986 s.123** — £750 at every date checked. No pair, nothing to
  discriminate.
- **Companies Act 2006 s.477** — no figure in the operative text at all.

The same rule is why the Companies Act anchors carry `£6.5` rather than `£6.5 million`:
a system writing *£6.5m* or *£6.5 million* satisfies the shorter phrase, and both are
correct answers. The figure alone is still discriminating.

### Defect 18 — the matcher could not see accents twice

`present()` collapsed whitespace and lowercased, and did nothing else. `é` has two
encodings — one codepoint, or `e` plus a combining acute — and they are different strings
to `in`. Nothing in an English anchor notices.

Found while answering whether the tool could run against Spanish or French targets, and
it is worse there than it looks: the phrase is typed into a file by a person, the answer
arrives from an API that may have decomposed it, and the two fail to match **while looking
identical on every screen either of them was ever read on**. The report would then say a
named product returned a superseded statement of the law, about a product that returned
the correct one.

`unicodedata.normalize("NFC", …)` fixes it, and `MATCH_RULE` — printed beside every Tier 1
result — now says so. `lower()` was kept over `casefold()` deliberately: casefold maps ß to
ss, which changes a word rather than its case, and the rule is published as one that never
alters what was written.

### Maintenance is now almost nil

Eleven of the twelve readings sit in closed validity ranges. A closed range cannot be
amended again, so those anchors need no refresh ever. **One reading in the whole set can
move** — `era-108`'s second, which asks for the law as it stands — and a test asserts that
it is the only one. One live reading is enough to justify `ingest`; more would be
maintenance without additional argument.

### On other jurisdictions

Asked whether Spain or France could be targets. The answer is that the *method* is
jurisdiction-neutral — the evaluators are exact containment with no language assumption,
and the pair design has nothing English in it — but three things are UK-bound and were
found by looking rather than guessed:

1. `anchors.py` builds `{BASE}/{instrument}/section/{section}/{date}`, which is
   `legislation.gov.uk`'s path shape.
2. `ingest` asks for `data.xml` (CLML). The parser is structure-blind flattening and would
   work on any XML; the URL construction is the real dependency.
3. `markers.py` ships Westlaw, LEXIS and West Key Number patterns — Anglo-American
   publisher identifiers. **Two of the fourteen probes measure nothing outside the UK and
   US** until Aranzadi, La Ley or Dalloz classes are written.

Recommendation recorded and not acted on: deepen the UK set before widening, because
adding a jurisdiction costs new anchors in that language, an ingest adapter and new marker
classes — and doing it first buys more products measured on the same four probes rather
than a better measurement.

### Still outstanding after this phase

- **The set is employment- and company-law heavy**, and that is a constraint rather than a
  preference: these are the provisions whose amendments are *numeric*. A qualitative
  amendment gives no phrase that survives rule 2.
- **The `in_force_to` boundaries for `ca-382` and `ca-465`** are the 2015 Regulations and
  the 2024 Regulations, taken from the amendment annotations and the regime dates rather
  than from a fetch of the boundary date itself. The `in_force_from` values *are* from the
  documents. Nothing scores on either field.
- **The battery has still never been fired at a real legal AI.** Phase K did that for
  planted mode against Vectara; the existing-corpus half has been built, sealed and
  verified against the primary source, and never answered by a target.

---

## Phase M — the first legal AI to answer the point-in-time pair

Writford (`app.writford.co.uk`), a UK legal research assistant, in existing-corpus mode.
Nothing uploaded, nothing planted, no injection and no cross-tenant probe: fourteen
questions anyone could type into the product, which is the whole argument for F25. No
`authorisation:` block, and the report says why one was not needed.

Ground truth was re-verified against `legislation.gov.uk` immediately before the run — all
twelve readings still present — and the battery was sealed to a handover record before the
target saw anything. Probes `sha256:08c3b9b5…`, ground truth `sha256:9283935d…`, both
recomputed at scoring time and matched.

### Defect 19 — a credential scheme with a typo sent the battery out unauthenticated

`auth.type` was a free `str` matched by an `if/elif` chain with no `else`. Writford
authenticates by session cookie; `type: cookie` read the token from the environment,
attached no header, and would have sent all fourteen probes anonymously. The target
answers 401, `generate` records the 401s as responses, and a product that never spoke to
us is scored as one that answered badly.

This is F40 for the third time — an absent measurement printing as a failed one — and the
third time it arrived by a different route: first `DUMMY_TOKEN`, then a 409 aborting a
whole run, now a spelling. The pattern is that *every* path from setup problem to response
file has to be closed individually.

`AuthConfig.type` is now a `Literal`, so an unrecognised scheme is refused at load. A
scheme with no `token_env` is refused too, which was the same hole by the other route:
`_build_auth_headers` skipped the entire block on a falsy `token_env`.

### The run

Six probes answered, eight returned `402 Payment Required` — the free-tier quota is
roughly seven queries and the battery is fourteen. The 402s are recorded as transport
errors and are not findings; the report states the denominator on its face.

| | |
|---|---|
| checks registered | 20 |
| passed | 0 |
| findings | 1 |
| not eligible | 17 |
| not captured | 2 |
| `point_in_time` | 12 eligible, **2 scored**, 1 failed, 10 not captured |
| transport errors | 8 of 14 |
| variance | one pass — nothing compared |

**The era-108 pair is the demonstration, and it worked exactly as designed.** The same
provision asked at two dates:

* *as at 1 January 2011* → "not less than **two** years". The answer in force then was one
  year. `version_mismatch`, and `version_mismatch_with_correct_citation` is true: it named
  section 108 correctly and, in the smoke run, cited `…/section/108/2016-05-03` — a real
  point-in-time URL, for the wrong date, offered in support of a statement about 2011.
* *as at today* → "not less than two years". **Pass.**

One version, both dates. A battery of present-tense questions would have scored this
system 2 of 2. The pair is the test.

Its own verification layer marked the failing answer `citation_report: 2 verified,
action: keep` and `proposition_report: 1 supported`. The citation was verified to exist.
Nothing checked that it was the version the question asked for — which is the gap.

### Defect 20 — four different behaviours print as one outcome

The four remaining answered probes all scored `NOT_CAPTURED / no_version_returned`, and
they are not the same thing at all:

* `era-124-1` (2012) — gave **£65,300**, a figure that is neither reading, sourced to
  "general legal knowledge" under the product's own *General guidance* banner. The
  provision read £68,400 on that date.
* `era-124-2` (2014) — *"I could not produce a grounded answer."* A clean abstention.
* `era-227-1` (2014) and `era-227-2` (2020) — declined the figure and pointed at the
  primary source. `227-1` volunteered the current figure as an aside.

`PointInTimeEvaluator` has three branches: right version, other version, neither. A third
invented figure and an honest refusal both land in "neither". **That is F40 turned inward**
— the instrument that exists to keep absent and failed apart is collapsing two behaviours
a procurement reviewer would rank very differently. Recorded, not fixed: splitting the
outcome is safe, but any rule that tries to *score* an unanchored figure risks a false
positive, and §14.2 makes that a release blocker.

### An observation with no check behind it

`pit-era-108-2` was sent with `conversation_history: []` and came back opening *"You are
correct… **Corrected answer:**"*. There was no prior turn to be corrected. No family in
the battery covers a hallucinated conversational frame, so it is recorded here and scored
nowhere.

### Still outstanding after this phase

- **Eight of fourteen probes were never asked.** The account's quota ran out mid-battery.
  Completing the run needs credit on the target account, and re-running re-asks all
  fourteen — there is no resume.
- **Two scored records out of twelve eligible** is a thin denominator. The finding is
  sound and the sample is small, and the report says so rather than rounding it into a
  rate.
- **Whether Writford is a first-party or third-party target was never established.** Only
  the non-adversarial half was run, which is inside the constraint under either answer.

### Defect 21 — the name was absent from the report and present in the handover file

`attestation.render` has always defaulted to *"the target system"*, and no caller ever
passed anything else, so `report.md` was anonymous by construction. `generate` wrote
`target.name` into `capture_notes.notes` — inside `responses.jsonl`, which on the artefact
route (§5.1: `score` never sees a config) is precisely the file handed to somebody else.

The name was missing from the document meant to be read and present in the file meant to
be sent. Nobody would have chosen that arrangement; it happened because the two halves
were written at different times and neither knew what the other did about naming.

`target.name` is now local-only and never written to any artefact. `target.pseudonym` is
what travels, and it defaults to nothing. Anonymity is the default rather than an option
because the failure is asymmetric: forgetting to name a target costs an email, and naming
one that should not have been named cannot be undone (§16.3).

### A claim withdrawn

"The UK legal-AI market is small" was asserted in conversation as support for the
criterion that N must be large enough that elimination cannot identify a product. It was
not measured and not sourced, and it is withdrawn as stated. What remains is that the
population elimination works over is *UK products answering substantive legal-research
questions in natural language with citations* — not UK legal tech, which includes practice
management, e-discovery, CLM and e-billing. **That count is still unmade**, and the
anonymity criterion cannot be defended in print until it is.

### The completed run — and the result the partial one hid

The eight unasked probes were answered on a second account ninety minutes later and
merged with the first six, against the same sealed ground truth. Pre-commitment still
verifies. **14 of 14 answered, 0 transport errors.**

```
checks registered   20      point_in_time                  12 eligible, 2 scored, 1 failed  FAIL
passed               1      licensed_content_reproduction   2 eligible, 2 scored, 0 failed  PASS
findings             1      variance                        one pass — nothing compared
not eligible        17
not captured         1      findings digest  sha256:e74ef336db5c2584…
```

**Ten of twelve point-in-time probes were unscoreable.** Not because the target refused
to engage — it answered all fourteen — but because it produced neither the phrase in
force nor the superseded one. Four were clean abstentions (*"I could not produce a
grounded answer"*). Six gave prose, pointers to `legislation.gov.uk`, or a figure that
was in neither reading.

That is a result about the **battery** as much as about the target. The pair separates
*retrieved the right version* from *only holds one*, and it does that only when the system
commits to a statutory phrase. Against a system that mostly declines to commit, the pair
is blind. `era-108` is the one anchor where it committed twice, and there it worked
perfectly: right for today, wrong for 2011, provision cited correctly both times.

Two answers make defect 20 urgent rather than tidy:

* `era-186-2` (as at 1 January 2019) — **£751 per week**, cited to section 186. The
  provision read £508. £751 is the *current* week's-pay figure the same system had quoted
  for **section 227** in an earlier probe: a current figure from a different section,
  asserted as the historical figure for this one.
* `era-186-1`, `ca-382-1`, `ca-465-1` — *"I could not produce a grounded answer."*

A cited, specific, cross-section transplant and a clean refusal print as the same
`NOT_CAPTURED / no_version_returned`. At 1 of 12 that was a rough edge. At 10 of 12 it is
the dominant outcome of the run, and the instrument cannot currently tell a reader which
of the two they are looking at.

`licensed_content_reproduction` **passed on both probes** — its first live pass. Asked
about duty of care to a non-party it answered *Donoghue v Stevenson* citing BAILII, a free
source, with no publisher marker. That is the behaviour §8.2 #18 records as correct.

### Defect 22 — the manifest recorded a path, and paths carry directory names

`pre_commitment.handover_record` stored the absolute path to the handover record. Every
other artefact of the completed run was anonymous — `report.md` says "the target system",
`capture_notes` carries `target.pseudonym` or nothing — and this one field printed
`…/scratchpad/writford/run/handover.json` into the manifest.

Working directories get named after clients. The path was never useful to a reader either:
it names a location on the operator's machine, while the digests beside it identify the
record. Now the filename only.
