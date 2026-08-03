# Threat model

Required by §12.2 of the plan, which says the model must be **stated precisely and split
by configuration**, because a blanket claim would be false in one of the two cases —
and *the splitting is itself the signal*. A vendor reading a security document that
draws its own limits accurately has learned more about the method than the report will
tell them.

This document is about what running this harness exposes. It is not a threat model of
your RAG system; that is what the harness produces.

---

## What the tool is

Five modes. Four of them never open a socket.

| Mode | Network | What it does |
|---|---|---|
| `plant` | none | Mints a synthetic corpus and the answer key from a seed |
| `hash` | none | Seals corpus, probes and answer key before any answer exists |
| `generate` | **your endpoint only** | Puts the probe file to a system you nominate |
| `score` | none | Reads a response file, writes a report |
| `schema` | none | Prints the published JSON Schemas |

`generate` is the only mode that talks to anything, and it is optional: the response file
can be produced by your own harness instead (§5.1.1). That is not a mitigation bolted on
afterwards — `plant`, `hash` and `score` import nothing from `transport/`, and the build
fails if that changes.

---

## Assets, by configuration

The two corpus configurations have genuinely different exposure. Collapsing them into one
statement would make the security claim either false or useless.

### Configuration A — planted corpus against staging

We generate synthetic legal documents, plant invariants in them, and you load them into a
staging index. The probes ask about those documents.

**What is at risk: nothing of yours.**

The documents are ours. The invariants are minted from a seed we hold. The queries ask
about entities that did not exist until we made them up. In the worst case — the tool is
entirely malicious and every control fails — it exfiltrates our own synthetic legal
documents back to us.

The residual exposure is not the corpus. It is:

| Asset | Exposure | Control |
|---|---|---|
| Your endpoint URL and any auth header | In the config, on the machine running `generate` | You hold it; it is never transmitted anywhere but your endpoint. Nothing is written to the response file except the request and what came back |
| Your staging index | Documents are added to it | You load them yourself. The harness uploads only through whatever ingestion path you point it at |
| Query volume against staging | ~19 probes per pass | Bounded and countable before the run — the probe file is handed over first |

### Configuration B — public-law probes against your real corpus

Probes drawn from published law and public authority, asked against your production or
production-like index over **your own documents**.

**What is at risk: your real content, and it must not be claimed otherwise.**

Answers come back containing whatever your system retrieved, and answers are what the
response file is made of. That file will contain material from your corpus. There is no
architecture that makes this untrue; the answer is egress control and custody, not a
claim.

| Asset | Exposure | Control |
|---|---|---|
| Your document content | Appears in answers, and therefore in `responses.jsonl` | Deny egress and run `generate` yourself; the file never leaves your machine until you send it |
| Retrieved chunks | Captured if your API returns them | Capture is yours to declare. Omitting them disables two checks rather than silently passing them |
| What you sent us | Whatever is in the file you chose to hand over | Read it first. It is JSONL, one record per line |

**This is the configuration where "we never see your data" stops being true.** Both
configurations are run because each covers the other's weakness (§9.1) — a planted corpus
proves the mechanism, a real corpus proves it happens on your documents — but only the
first one carries the strong claim, and it should never be stretched to cover the second.

---

## Adversaries considered

### 1. This tool is malicious or compromised

The one you should assume. Nobody should run an unaudited binary against a live legal
system on the author's assurance.

| Control | Where |
|---|---|
| You are not required to run it at all | §5.1.1 — send us a `responses.jsonl` from your own harness |
| Four of five modes have no transport dependency | Asserted by `tests/test_dependency_boundary.py` and by a CI run inside an empty network namespace |
| The scoring path has no remote vendor, credential or endpoint | `scripts/check_no_remote_scoring.sh` |
| 14 pinned, hash-verified dependencies in the layer you install | `requirements/generate.txt`, `scripts/check_pins.py` |
| Every dependency's bytes are fixed | `pip install --require-hashes` |
| The artefact you install is the one the public workflow built | `scripts/verify_release.sh` |

Under denial of egress, a delayed payload still has to make a call eventually and fails
whenever it fires. **Timing is irrelevant under denial**, which is why the ask is "deny
egress", not "disconnect for an hour".

### 2. A dependency is compromised upstream

| Control | Limit |
|---|---|
| Exact pins plus per-file hashes | Fixes the bytes; does not make them good |
| Weekly `pip-audit` on all four lockfiles | Finds published advisories; finds nothing unpublished |
| The `generate` layer is 14 packages | A smaller set to be wrong about |
| SBOM per layer, CycloneDX 1.6 | Lets you run your own scanner against the set |

**What this does not cover:** a dependency that was already backdoored when it was
pinned. Hash-pinning fixes what you receive, not whether it was ever trustworthy.

### 3. The release pipeline is compromised

| Control | Limit |
|---|---|
| GPG-signed tag, verified before the build starts | Rests on the key at `.github/release-signing-key.asc` |
| SLSA build provenance from a public workflow | Issued by GitHub's OIDC identity, not by us |
| Cosign signature in the public Rekor log | A signature made privately is visible as an absence |
| Actions pinned by commit SHA, not tag | A tag is a mutable pointer |
| Release job permissions scoped to one job | `contents: read` everywhere else |

**What this does not cover:** a compromise of the maintainer's signing key or GitHub
account. Provenance would then be genuine and the artefact still hostile. Nothing in a
single-maintainer project solves that; the honest mitigation is that all of it is public,
so a fraudulent release is a permanent public record rather than a private one.

### 4. The operator — us — oversteps

Not a supply-chain risk, and the one most likely to actually cause harm.

| Control | Where |
|---|---|
| Probe families classed by authorisation requirement | §13; enforcement lands in Phase I |
| Use of a product is not authorisation to test it | §16.1 — stated to the target before anything runs |
| The probe file is handed over before the run | You see every question before it is asked |
| The report says what was asked, verbatim, and whether it was asked as written | `probes_asked_verbatim` in every run manifest |

### 5. The findings are wrong

Also a threat — a false accusation against a vendor is a real harm, and one this project
takes as seriously as a missed defect.

| Control | Where |
|---|---|
| Tier 1 findings involve no model at any point | An AST test fails the build if a Tier 1 evaluator can reach one |
| Every finding quotes the material behind it | The evidence bundle |
| The answer key is sealed before any answer exists | `hash`, and `score --handover` aborts on a mismatch |
| What could not be scored is `NOT_CAPTURED`, never a pass | F40 |
| Checks that need material we do not have are stated as unscored | e.g. citation counter (b) |

---

## Out of scope

- **Denial of service against your endpoint.** ~19 probes per pass. If that is load, say
  so and we will pace it — but it is not what this is designed to avoid.
- **Testing systems you do not control.** See §13. Do not.
- **The security of your RAG system.** That is the output, not the threat model.
- **Multi-tenant isolation of this tool.** There is no service. It runs on one machine at
  a time, owned by whoever ran it.

---

## Retention

What we hold after an engagement, and for how long, is settled **before** the first run —
not afterwards (§15.7). If it has not been agreed in writing, do not send us a response
file drawn from a real corpus.
