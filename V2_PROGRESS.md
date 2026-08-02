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
| **B2** | Hardened invocation, SBOM, signed tags + SLSA + cosign, CI scanning | 1 d | 🟡 lockfile done; SBOM, signing, CI outstanding |
| **C** | Tier tagging + report v2 + manifest/hashing + GPG-signed releases | 2.5 d | ✅ 2026-08-02 *(signed releases are Phase B2; Docker deferred)* |
| **D** | Seeded plant generation + collision guard; rewrite evaluators 4–14 | 4 d | ⬜ |
| **E** | N-pass execution + variance reporting | 1 d | ⬜ |
| **F** | `validate` mode | 0.5 d | ⬜ |
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
