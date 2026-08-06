# What we will and will not run, and what we keep

Two questions a buyer asks before anything else: *what are you going to do to my system*,
and *what happens to what comes back*. This page answers both, and the first answer is
enforced by the software rather than promised in prose.

## The line: use is authorised, testing is not

Signing up for a product authorises **use**. It does not authorise testing. Most SaaS
terms separately prohibit benchmarking, automated access and multi-account creation, and
probing tenant isolation on a system we do not own is a **Computer Misuse Act 1990**
exposure. *"I signed up for a trial"* is not authorisation.

| Safe — indistinguishable from ordinary use | **Never** on a self-signed-up account |
|---|---|
| Ask legal questions, read the answers | Prompt injection payloads |
| Check whether returned citations resolve | Cross-tenant canaries — needs two accounts, probes isolation |
| Check point-in-time correctness against public law | Uploading adversarial documents |
| Ask about topics outside the corpus | High-volume or automated querying |
| Ask the same question three times and diff the answers | Replacing a document in a live index |
| Check whether answers carry publisher-proprietary markers | Anything touching another tenant |

Everything in the right column requires written authorisation, which by definition puts it
inside a paid engagement.

## How the tool enforces it

Not by asking nicely. `generate` refuses to send a single request until the condition is
satisfied, and the refusal names every reason.

**Two things make a run need authorisation, and they are independent.**

1. **The families it asks.** `src/legal_rag_audit/authorisation.py` classes every probe
   family by what running one actually does to somebody else's system. The classification
   is data, not a comment, and a test asserts every family both batteries ask is
   classified. An unrecognised family is treated as needing authorisation — the safe
   reading of *nobody has decided* is not *this is ordinary use*.
2. **Whether it uploads.** A planted battery puts our documents into their index, and one
   of those documents carries an injection payload by construction. That is *uploading
   adversarial documents*, whatever families ride on it.

**Production needs a second, separate act.** `environment: production` in the config is
not enough; `--i-have-written-authorisation-for-production` has to be typed on the command
line as well. A config is copied between runs and a command line is typed for one.

**`validate` never needs authorisation.** It fires three neutral throwaway probes and
cannot reach the battery — the neutral probe set is a constant in a package with no import
path to `probes/`, `plants/` or the corpus, and a test asserts that. This is what makes it
free as a pre-sale compatibility check.

**The existing-corpus battery never needs authorisation either.** It uploads nothing,
needs no `upload` endpoint, and every family on it is ordinary use: point-in-time
correctness against public legislation, citation resolution, parametric bleed, abstention,
non-determinism, licensed-content reproduction. That is not a coincidence — it is why
§9.1's second configuration exists, and why it is the half that can be run before anybody
has signed anything.

## What the report carries

The authorisation block is reproduced **verbatim** in the run manifest and printed in the
attestation, so the artefact carries its own provenance of consent. A report that names a
cross-tenant leak and cannot say who authorised the test that found it is a report nobody
should have produced.

```yaml
authorisation:
  authorised_by: "Name, Role"
  authorised_on: "2026-08-06"
  environment: "staging"          # dev | sandbox | staging | production
  scope_ack: "injection, canary and upload probes authorised in writing"
  reference: "engagement letter 2026-03, clause 4"   # optional
```

**What this is not.** A populated block is not evidence that anybody was actually
authorised — a determined operator can type a name into a YAML file. What the control does
is make the crossing **deliberate and recorded**. An accident cannot produce it, and a
misrepresentation is on the record. The attestation says so on the page rather than
letting the block imply more than it establishes.

Where a battery needed authorisation and the response file carries none — which happens
legitimately on the artefact route, where the target runs their own harness against their
own system — the report says that under *Limits*. It does not refuse to score: by the time
a response file exists the requests have been sent, and refusing to read it would not
un-send them.

**No expiry is enforced.** The manifest records how old the authorisation was on the day
of the run and leaves the reader to decide whether a scope from two years ago still covers
it. Any expiry we invented would be a number of ours presented as a standard, which is the
mistake this project exists to find in other people's reports.

## Retention

`responses.jsonl` is client material even when the corpus is ours.

- **Responses are held only as long as needed to produce and defend the report — 90 days
  from delivery**, then deleted.
- **Verbatim excerpts quoted in the report are retained with the report** for as long as
  the client holds it. A report whose evidence has been deleted is not defensible.
- **No client responses are used for any other purpose.** No aggregate publication of a
  named client's data, and no publication at all without written consent.
- **Nothing is sent anywhere.** Scoring runs offline with sockets disabled, enforced in
  code and checked in CI. There is no inference vendor and no sub-processor in the
  scoring path.

## Published results

Configurations, never named commercial products. A published benchmark describes what was
run and what came back; it does not name whose system produced it. That holds whether the
result is good or bad, and it is not negotiable per engagement — a rule that bends once
is a rule a reader cannot rely on.
