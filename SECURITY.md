# Security

This project asks people to run software against systems they are responsible for. That
is the hardest thing in the offer, and *"it's open source"* is not an answer to it —
anyone can publish code, and stars measure popularity rather than safety.

So the position is not *trust us*. It is: **every claim below has a command next to it,
and the command works in a clone you made yourself.** Where something cannot be checked
mechanically, it says so instead of being written more confidently.

The shortest version: **you do not have to run it at all.** See
[the artefact route](#the-shortest-answer-dont-run-it) below.

---

## Reporting a vulnerability

Email **abdullah@memonsystems.com**. Include what you found and how to reproduce it.

Expect an acknowledgement within 3 working days and an assessment within 10. If a fix is
warranted it ships in a patch release with the finding credited, unless you ask
otherwise. There is no bounty programme.

**Please report privately first.** If a report affects an engagement client, they are
told before disclosure, because a finding in this tool is a finding in something they
were persuaded to run.

---

## The shortest answer: don't run it

Four of the five modes never touch a network, and the one that does — `generate` — is
optional. If your policy is that unreviewed third-party software does not touch a live
system, that policy can be honoured in full:

1. We send you a probe file and a JSON Schema. Text and a spec, not executables.
2. You produce a `responses.jsonl` however you like. Thirty lines of curl is enough.
3. We score it offline.

Nothing of ours executes anywhere near your endpoint. This is
[§5.1.1 of the plan](V2_FULL_PLAN.md) and it is asserted structurally rather than
promised: `tests/test_dependency_boundary.py` runs `plant → hash → score` in an
environment with `httpx` uninstalled, and CI runs the same route inside an empty network
namespace where a socket call fails rather than resolving.

```bash
python3 .github/scripts/artefact_route.py --allow-network   # locally
```

---

## Supported versions

| Version | Supported |
|---|---|
| `main` / latest release | Yes |
| Anything older | No |

This is pre-1.0 software with a single maintainer. There are no backports. If you are
running a release older than the latest, upgrade rather than asking for a patch.

---

## Verifying a release

Every release artefact is signed, and the signatures are verifiable by a stranger with
public tooling. One command:

```bash
./scripts/verify_release.sh v0.2.0
```

It checks four things, and none of them is our word:

| Check | What it establishes | Whose word it rests on |
|---|---|---|
| GPG tag signature | Who published this | A key committed at `.github/release-signing-key.asc` — compare the fingerprint below |
| SHA-256 checksums | This is the same file | Arithmetic |
| Cosign signature | It was signed by a run of `release.yml` in this repository | Sigstore's public Rekor transparency log — a signature made privately would show up as an absence |
| SLSA build provenance | These exact bytes came out of that workflow at that commit | GitHub's OIDC identity, which we cannot mint |

**Release signing key**

```
A487 3AE7 AEE6 56BF F54E  C751 B5C9 93EA B678 58DE
Abdullah Memon <abdullah@memonsystems.com>
ed25519, expires 2028-07-28
```

The expiry is stated because it matters: after that date old signatures remain valid but
new releases will be signed by a successor key, and a successor key you have not seen
before is exactly the thing to be suspicious of. It will be announced in a release signed
by this one.

**What verification does not establish.** That the software does what the README says. It
establishes only that what you downloaded is what the public workflow built from the
public signed commit. The rest is what the tests, the repository gates, and every
report's own limits section are for.

---

## Supply chain

### Dependencies are pinned to bytes, not to ranges

There is no `>=` anywhere in the installed set. Every requirement is `==`, and every
lockfile entry carries the SHA-256 of each distribution file, so `--require-hashes` fails
the install rather than letting a substituted artefact reach a run.

```bash
python3 scripts/check_pins.py
```

That gate asserts five properties: nothing is loose, `pyproject.toml` agrees with the
lockfiles, every entry is hashed, the base install is the `generate` layer and no more,
and the four layers agree with each other on shared packages.

A range would also make a vulnerability scan a statement about the day you installed
rather than about the artefact — which is how `idna` 3.11 (PYSEC-2026-215) came to be
installed here while the declared dependency set looked clean.

### The dependency set is small on purpose

| Layer | Packages | Who installs it |
|---|---|---|
| `generate` | 14 | **A target.** Five pure-Python libraries and their transitive set — no compiled extensions, no ML stack |
| `score` | 66 | Us, offline. Adds the local scoring models |
| `dev` | 92 | Contributors. Adds test and release tooling |
| `audit` | 100 | CI only. The security scanners |

The `generate`/`score` split is a hard boundary, not a convention:
`tests/test_dependency_boundary.py` builds a `generate` environment and asserts torch,
transformers, sentence-transformers and numpy are not importable in it. It is what makes
*"read the whole thing in an afternoon"* literally true for the layer that lands on
someone else's machine.

### SBOM

CycloneDX 1.6, one per layer, committed at [`sbom/`](sbom/) and attached to every
release.

One per layer rather than one for the project, because a merged SBOM listing torch would
misdescribe what a target installs — which is the only question they are asking.

```bash
python3 scripts/gen_sbom.py --check    # the SBOMs still describe the lockfiles
python3 scripts/validate_sbom.py       # they are valid CycloneDX 1.6 (needs the audit layer)
```

They are generated from the lockfiles rather than from an installed environment: an
environment SBOM describes whatever happened to be on the machine that ran the scanner.
They carry the real resolution graph, so you can see that torch arrives through
`sentence-transformers` rather than because we asked for it.

Deliberately **not** in them: `metadata.timestamp` (it would change on every generation
and make drift undetectable — the build time of a released artefact is in its SLSA
provenance instead) and component licences (a lockfile carries no licence metadata, and
reading it from installed distributions would make the document depend on a machine
again). Both absences are recorded inside each document rather than left to be noticed.

### Continuous scanning, with linkable runs

[**Security workflow runs →**](https://github.com/azterizm/legal-audit-rag/actions/workflows/security.yml)

| Tool | Scope |
|---|---|
| `pip-audit` | Each of the four lockfiles, audited separately |
| Bandit | `src/legal_rag_audit` |
| Semgrep | `p/python`, `p/security-audit` |
| Trivy | Filesystem scan, **and both container images**, scanned separately |

Scheduled weekly as well as on push. A dependency set that was clean when it was pinned
does not stay clean, and because the pins are exact by design, a new advisory is
something only a scheduled scan will surface — nothing quietly resolves past it.

**Link the runs, not a badge.** A badge asserts a state. A link shows you the command,
the version, the output and the date, and lets you re-run the whole thing on a fork.

**One thing here is not pinned, and it should be said plainly.** Semgrep's *rules* are
fetched from the public registry when the job runs, so a Semgrep result is scoped to the
rules published that day. The scanner version is pinned and hashed like everything else;
the ruleset is not.

### CI actions are pinned by commit SHA

Every `uses:` in every workflow is a 40-character commit SHA, never a tag. A tag is a
mutable pointer — an action referenced as `@v5` runs whatever its owner moves that tag
to, which is the same substitution `--require-hashes` exists to prevent one layer down.
`tests/test_supply_chain.py` fails the build if an unpinned reference appears.

Workflow permissions are `contents: read` by default. The elevation a release needs
(`contents: write`, `id-token: write`, `attestations: write`) is scoped to one job in
`release.yml`.

---

## Running it against a live system

**Start with `validate`.** Three neutral throwaway queries and one small neutral file,
named `legal-rag-audit-validate.txt`, uploaded so the harness can tell you whether your
upload endpoint issues document identifiers — `--skip-upload` suppresses that, and the
output then says the question went unanswered. No battery probe is fired, no planted
corpus is uploaded, and nothing is written to your disk. The `validate` package has no
import path to the battery, the planting code or the corpus loader, and a test walks the
import graph to keep it that way: raw response bodies print to your terminal, so anything
from the battery reaching that surface would be our problem, not yours.

If you then choose to run `generate` against your own endpoint, the controls that
actually answer the fear are enforcement, not requests. *"Turn off the internet"* does not answer
a delayed payload; **denying** egress does, because a delayed payload still has to make a
call eventually and it fails whenever it fires.

| Control | Why it answers the actual fear |
|---|---|
| Egress denied, single allowlisted host — your endpoint | Timing becomes irrelevant under denial |
| A logging proxy in front of it | The connection log proves what it talked to. *Your* log, not our claim |
| Non-root, read-only filesystem, all capabilities dropped, no new privileges | What a security engineer actually looks for |
| One read-only input mount, one write-only output directory, exits when done | Nothing persists — nowhere for "queued" to live |

**Two images, and only one of them is for you.**
`legal-rag-audit-generate` carries five pure-Python libraries and is the only one that
talks to your system; `legal-rag-audit-score` adds the ML stack and opens no sockets at
all. Both run as UID 65532, install under `--require-hashes` from a base image pinned by
digest, and are cosign-signed **by digest** with SLSA provenance attached — verify before
you pull with `./scripts/verify_release.sh <tag>`. `trivy image` scans each one on every
push and uploads a CycloneDX SBOM of it, including the OS packages that no lockfile of
ours describes.

The dependency boundary is checked inside the image rather than in a lockfile:
`tests/test_container.py` imports `torch`, `transformers`, `sentence_transformers` and
`numpy` in the built generate image and requires each to fail.

**One correction worth making explicitly.** An earlier version of this page and of the
README printed `--network=host-allowlist-only`. There is no such Docker network, and
**Docker cannot express a per-container host allowlist at all.** What it can express is
no external route: `docker network create --internal audit-net`. Your forward proxy on
that network is then the only way out, and the allowlist and its log are yours.
[`docs/hardened-run.md`](docs/hardened-run.md) has the invocations, each flag's purpose,
and what none of them establishes.

`plant`, `hash` and Tier 1 `score` all run in the *generate* image with `--network=none`,
which is the artefact route above, in a container — and it remains the stronger answer,
because there the question of what our code might do on your machine does not arise.

**No credentials are needed and none should be given.** The harness talks to one endpoint
you nominate. It has no account system, no telemetry, and no remote scoring path; scoring
runs locally and offline, and `scripts/check_no_remote_scoring.sh` asserts there is no
vendor, credential or endpoint anywhere in the scoring code.

---

## Threat model

Split by configuration rather than claimed as a blanket property — see
[`docs/threat-model.md`](docs/threat-model.md). The summary:

- **Planted corpus against staging:** the documents are ours. Worst case — the tool is
  entirely malicious — it exfiltrates our own synthetic legal documents back to us. There
  is nothing of yours to steal.
- **Public-law probes against your real corpus:** that is not true, and it is not
  claimed. Your real content is in scope, and egress control is the answer.

---

## Authorisation

Do not point this at a system you are not authorised to test. Use of a product is not
authorisation to test it, and the tool enforces that boundary rather than describing it:
probe families are classed by authorisation requirement, and the classes that need
written permission are gated (§13 of the plan; the enforcement lands in Phase I).

If you received a report about a system you operate and did not authorise the testing,
email the address above — that is a defect in how the engagement was run, and we want to
know.
