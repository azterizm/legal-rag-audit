# bundled-demo — the try-it corpus

Fourteen synthetic documents, uploaded clean and queried immediately. This is what
`legal-rag-audit plant` produces when nothing else is named, and it is what any report
labelled *demo* was generated from.

**It is a demo, not an audit.** That is a promotion rather than a demotion: a demo is a
thing this corpus can honestly be, and an audit is not.

## What a clean run of it establishes

That the harness works end to end against your endpoint — that the probes reach your
system, that the answers come back in a shape the extractor can read, and that the checks
score them. That is worth having, and it is the whole of it.

## What a clean run of it does not establish

Read this list before quoting a number from a bundled run anywhere.

- **Not your corpus.** Fourteen short synthetic documents are not your production
  ingestion history. A system that handles these cleanly can fail badly at forty thousand
  documents, on your chunker, with your index.
- **Not your domain.** These documents belong to no practice area and no jurisdiction.
  The words in them were chosen to be easy to plant in, not to be law.
- **Not unguessable.** The seed is published (`plants.pipeline.PUBLISHED_DEMO_SEED`) so
  that anyone can regenerate this corpus and check it against the one they were sent. That
  is correct for a demonstration and disqualifying for an engagement: a battery whose
  invariants are public cannot claim its plants could not be pre-empted. An engagement
  supplies its own seed and the ground-truth manifest records which of the two was used.
- **Not compliance.** No generic corpus can tell you whether you are compliant. The
  questions that decide that are about *your* obligations against *your* documents, and
  nothing here knows either.

A vendor who runs this and sees failures has learned something real and has no way to know
which of them matter. That is the honest end of a free run, and the report says so on its
own face rather than implying more.

## Composition

Fourteen documents filling the roles in [`../../spine.py`](../../spine.py), which is where
each one's purpose is recorded. §9.4's nine-line composition table maps onto them:

| Role | Documents |
|---|---|
| Contradiction surfacing | `supplier_agreement_v1.txt`, `supplier_agreement_v2.txt` |
| Structural integrity | `service_schedule.md` |
| Retrieval disambiguation | `statute_alpha.txt`, `statute_beta.txt` |
| Entity masking re-hydration | `settlement_schedule.txt` |
| Injection resistance | `internal_memo.txt`, `vendor_notice.txt` |
| Citation integrity | `authority_digest.txt` |
| Cross-tenant leakage | `tenant_a_matter.txt`, `tenant_b_matter.txt` |
| Routing contamination | `namespace_x_note.txt` |
| Context memory | `matter_chronology.txt` |
| Index freshness | `retainer_notice.txt` and its revision |
| Parametric bleed, abstention | *the absence of a document* — see `out_of_corpus` in `corpus.yaml`, and Statute Alpha's declared absence of an Article 12 |

The prose is deliberately thin. The only load-bearing content is the invariant at each
declared slot: every check scores a token, not a paragraph, so a document that tried to be
realistic legal drafting would make the battery harder to reason about without making any
check stronger.

## Its predecessor

Until Phase H this name belonged to thirteen hand-written documents under
`src/legal_rag_audit/corpus/`, carrying expectations typed into the battery by hand. Phase
D replaced those expectations with seeded plants and left the thirteen files loaded by
nothing. They were retired, and the name moved to the corpus that the free run actually
uses. Their content is in the git history.
