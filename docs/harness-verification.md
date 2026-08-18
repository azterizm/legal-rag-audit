# Verifying the harness

The question after *"is it safe to run against my system?"* is *"how do I know your tool
is right?"* This page is the answer, and it is mechanical rather than rhetorical: a
reference target ships in the repository, it can be told to exhibit each failure mode the
battery claims to find, and two gates run against it on every push.

- **Sensitivity** — with a pathology switched on, the check that looks for it reports it.
  Every registered check, no exemptions.
- **Specificity** — with the target behaving correctly, **no check reports anything**.

The second is the one that costs money to get wrong. A missed detection is a bug; a
finding raised against a system that did nothing wrong is a report we should never have
sent, so a false positive here blocks a release and a missed one does not.

Both numbers are about our instrument, not about anybody's product. They are published
for the same reason a Tier 2 finding carries the model name and the threshold: a claim
about measurement that does not state its own error characteristics is not a measurement.

## The reference target

`tests/mock_target/` — a small local server speaking the same three endpoints a real
target does (`/upload`, `/chat`, `/retrieval`). It is not a simulation of a RAG system.
It is an oracle: it looks each question up and answers correctly, and each profile makes
it answer one question wrongly in one specific way.

What makes a clean run mean something is the information it is allowed:

| It holds | It does not hold |
|---|---|
| The probe file — the questions, exactly as a target receives them | The ground-truth manifest |
| The documents that arrived at `/upload` | The expectations, the plant values, or any part of the answer key |

The invariants it answers with are recovered **from the uploaded bytes**, by aligning
each document against the template it was planted from. So the corpus, the questions and
the answer key are three separate artefacts that have to agree for a run to come out
clean — an oracle that answered out of `ground_truth.json` would make the specificity
gate a test that the scorer agrees with itself, which is worth nothing. A test asserts
the mock's imports, so this cannot quietly stop being true.

Every gate run is a full run: corpus planted to disk, uploaded over HTTP, answered,
captured through the transport client's JSONPaths, written to `responses.jsonl`, scored
offline against a key built from the same seed. Each seam between those is a place a real
engagement breaks, and none of them is exercised by a fixture.

## The matrix

| Profile | Behaviour | Check that must fire | Also trips |
|---|---|---|---|
| `leak_tenant_b` | Includes tenant B chunks in tenant A retrieval | `cross_tenant_leakage` | — |
| `follow_injection` | Obeys instructions found in documents | `injection_resistance` | — |
| `fabricate_citations` | Emits plausible IDs not in the upload manifest | `citation_integrity` | — |
| `stale_index` | Serves pre-update content after re-upload | `index_freshness` | — |
| `swap_counterparties` | Re-hydrates the wrong entity | `entity_masking` | — |
| `parametric_answer` | Answers from world knowledge with no citation | `parametric_bleed`, `abstention` | — |
| `ignore_namespace` | Ignores namespace scoping | `routing_contamination` | — |
| `pick_one_silently` | Returns one side of a contradiction | `contradiction_surfacing` | — |
| `merge_sources` | Synthesises without per-claim attribution | `attribution` | — |
| `drop_exclusion` | Omits the qualifying clause | `clause_synthesis` | — |
| `naive_chunking` | Severs header from leaf | `structural_integrity` | — |
| `collide_articles` | Merges Article 5 across statutes | `disambiguation` | — |
| `wrong_referent` | Resolves the pronoun to the wrong antecedent | `context_memory` | — |
| `slow_regenerate` | Long TTFB→total gap on contradictory queries | `latency` | — |
| `unsupported_prose` | Adds fluent, unsupported sentences | `unsupported_assertions` | — |
| `irrelevant_chunks` | Returns off-topic retrieval | `retrieval_relevance` | `unsupported_assertions` |
| `serve_licensed_content` | Returns publisher editorial markers in retrieved chunks | `licensed_content_reproduction` | — |
| `invent_an_instrument` | Describes a section of a statute that does not exist | `abstention` | — |
| `answer_current_law` | Serves one version of a provision whatever date is asked about | `point_in_time` | — |
| `nondeterministic` | Varies invariant outcomes between passes | `response_divergence` | `disambiguation` |
| `clean` | Behaves correctly on every probe — the false-positive control | — | — |

`answer_current_law` is not in the plan's table. Point-in-time correctness is F27's
*distinct evaluator* rather than one of §8.2's eighteen, so it arrived with no pathology
beside it — and the gate, being written against the check register, refused to build
until one existed. That is the mechanism working rather than a gap being noticed.

`invent_an_instrument` is not in it either, and it is a different kind of absence. The
check it fires, `abstention`, has been in the register since Phase B and already has a
profile — but that profile rewrites `conf-001`, a question about a corpus we uploaded, and
so it cannot reach the ten no-upload probes that ask about statutes nobody wrote. The gate
is written against the check register, and the register counts checks rather than
configurations, so it would have stayed green with those probes exercised in the passing
direction only. Which is the quieter way for a check to stop working.

### Two batteries, because neither covers the register alone

§9.1 says to run both configurations and this is where that becomes concrete. The
**planted** battery authors documents and uploads them, which is the only way to get
canaries, injection payloads and contradiction pairs. The **existing-corpus** battery
uploads nothing at all and scores against public ground truth — point-in-time phrases
quoted from `legislation.gov.uk`, a published set of publisher-assigned identifiers, and
a set of instruments that are not on the register at all.

Two checks are eligible only on the second, so the gate runs both, and the clean control
runs on both. Each battery reports the other's checks as `NOT_ELIGIBLE` rather than as
passes: F40 applied at the level of a configuration rather than a probe.

A third check, `abstention`, is eligible on both and means different things on each. On
the planted battery it asks about an article of an uploaded statute that the statute says
it does not have. On the existing-corpus battery it asks about a statute that does not
exist, with nothing uploaded — so a specific answer did not come from the index and did
not come from the law, and there is no third explanation. Same evaluator, same check
name, and the harder finding of the two is the one that needs no corpus.

The existing-corpus config declares **no `upload` endpoint at all** — not an unused key,
an absent one — so a run that tried to upload could not have resolved a URL to send to.
That is F25 asserted as a property of what the target had to expose, rather than as a
claim about how our code behaves.

### The licensed-content check has two controls, and they are the point

A finding here says a company's index holds material whose licence sits between them and
a publisher. Get it wrong and it is an allegation of unlawful conduct against a named
company (§16.3), so two of the three outcomes are deliberately **not** findings and both
are exercised:

- **`external_fetch`** — the marker appears, cited to the publisher's own service. That is
  the licensed thing working. It passes.
- **`unattributed`** — the marker appears with no citation and no retrieval evidence.
  Consistent with an index holding the licensed edition *and* with the model reciting
  from weights; this check cannot separate them, so it reports `NOT_CAPTURED` rather than
  picking the reading that produces a finding.

**The gate is written against the check register, not against this table.** Shipping an
evaluator without a pathology profile fails the build rather than quietly shrinking the
denominator. This page is checked against the code on every run for the same reason.

### The two columns on the right

**"Also trips"** is declared, not tolerated. A profile that failed six checks would make
the matrix unreadable — you could not tell which evaluator caught what — so each profile
is asserted to fail *only* what it names here. Two side effects are unavoidable and
therefore stated: an answer cannot be entailed by chunks about something else, so
replacing the retrieval trips the entailment check too; and the pass on which a
non-deterministic target moved is a genuine failure on that pass, which is what makes it
a divergence rather than a rewording. The gap the second one rests on is the one NF2
names: scoring is deterministic and asserted to be, target systems typically are not, and
`response_divergence` exists to report that difference as a finding rather than let it
read as flakiness in the tool.

**`latency` is detected differently, and the reason is in the check.** It is a
measurement (§8.2 #15): there is no pass threshold, because any threshold would be ours
rather than a standard, so it cannot report `FAIL` and a gate demanding that it did would
be unsatisfiable by design. What it produces instead is the paired reading — the
contradictory query taking materially longer than the baseline — and that reading firing
is the detection. The gate branches on whether a check *is* a measurement rather than on
its name, so a second one added later is covered without anyone remembering this page.

## What these numbers do not establish

They are about the scorer and the interchange path. Read narrowly:

- **Not that the battery is complete.** Every check catches the defect it was pointed at.
  Nothing here says the eighteen checks are the right eighteen, or that a system passing
  all of them is sound. §8.2 names three failure modes that ship unscored, and they stay
  unscored whatever the sensitivity number says.
- **Not that a real system fails the way the mock does.** Each pathology is a
  hand-written caricature of a defect. A real retriever severs a heading from a leaf in
  ways nobody enumerated, and a check that catches the caricature may miss the real
  thing. This measures that the instrument responds to the signal it was built for, not
  that the signal is the whole phenomenon.
- **Not that the corpus is representative.** The reference target is planted from one
  seed against the bundled templates. §9.5 is where a corpus earns the right to support a
  claim about a practice area; this earns nothing of the kind.
- **Not a claim about Tier 2 stability.** The two model-backed rows load checkpoints
  resolved by name rather than pinned by digest — a gap the run manifest records rather
  than hides — so their verdicts can move under us when the weights behind a name change.

## Reproducing it

```bash
python3 -m pytest tests/test_reference_target.py -q
```

Twenty-odd seconds, no network, no models, nothing to configure. Both gates run on every
push as their own CI check, and again in the release workflow before anything is signed —
a build that cannot find planted defects, or that invents findings against a target
behaving correctly, does not get released.

The two Tier 2 rows are the exception, and they are opt-in:

```bash
LEGAL_RAG_AUDIT_TIER2_GATE=1 python3 -m pytest tests/test_reference_target.py -q
```

They load checkpoints resolved by name rather than by digest, so the first run fetches
several hundred megabytes from a third party. That runs in one CI job and not in the
release path: a pipeline built to eliminate mutable references should not acquire one by
downloading unpinned weights on the way to signing an artefact. Where the flag is unset
the rows skip and name the two checks they did not verify, rather than passing quietly.
