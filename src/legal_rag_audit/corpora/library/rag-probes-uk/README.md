# rag-probes-uk — the fictional-instrument corpus

Fourteen documents in the shape of an English corporate matter, in which **every
instrument, party and figure is invented**: two fictional statutes whose section 42s
collide and whose subject matter does not, a SaaS subscription agreement in two executed
states, a share purchase agreement with a nested indemnity schedule, two structurally
parallel transaction files in separate workspaces, two candidate CVs carrying buried
instructions, and a fee notice that is revised mid-run.

```bash
legal-rag-audit plant --corpus rag-probes-uk --seed <your seed> -o ./run
```

## What a run of it establishes

**That the pipeline is grounded.** No index anywhere holds the Ravensbourne Commercial
Tenancies Act 2019, so a system that answers about it confidently without retrieving these
documents has fabricated the answer — there is no third explanation. That is the property
a corpus drawn from real law cannot have, because a model may know real law from its
weights and look like it retrieved.

It is also the corpus to reach for when the target is **not a legal product**. A retrieval
platform with no legal index of its own can still be measured here, because every answer
has to come from documents the operator put in it. `employment` and
`commercial-contracts` ask what a practice area asks; this one asks whether the machinery
underneath works at all.

## What it does not establish

- **Nothing about law.** Not a single sentence here states a legal position, and that is
  deliberate. A system can hold the whole of this corpus perfectly and be wrong about
  every real question a client asks. For law, run a practice-area corpus, and run
  `plant --mode existing` against `legislation.gov.uk`.
- **Not your drafting.** These agreements are three clauses long.
- **Not your corpus at scale.** Fourteen clean documents is not an ingestion history.
- **Not a vendor's production index.** It characterises a pipeline on documents we
  supplied.

## Staleness

`staleness_triggers` is empty, and here that is the finding rather than an omission.
Parliament cannot amend the Blackmere Financial Oversight Act 2021. This corpus needs no
re-run trigger, no monitoring retainer and no `as_at` caveat about the law — the only
thing that could date it is the drafting conventions it imitates.

It is the only working corpus in this library with that property. `bundled-demo` shares it
and is a demonstration; this one is meant to be run.

## Provenance

Document shapes and several invariant positions are adapted from the published battery at
[azterizm/rag-security-probes](https://github.com/azterizm/rag-security-probes) (Memon
Systems Ltd, Mode A) — the colliding section 42s, the Project Titan indemnity schedule, the
restricted transaction file and the CV injection payload all originate there.

**The values do not.** The published battery carries fixed literals; every invariant here
is minted from `corpus.seed` and collision-guarded like any other corpus in this library.
That distinction is the whole reason for porting the shapes rather than pointing at the
repository: the published set is public, and its own README says publication contaminates
it — *"A passing result is a self-assessment, not audit evidence."* A seeded run of these
shapes is not answerable from having read the repository, so it can carry a number the
published set cannot.

## Two families the upstream battery has and this corpus does not

Porting shapes onto the spine covers seventeen of the upstream battery's shapes and leaves
two behind, because no evaluator in this build scores them:

- **Lost-in-the-middle** (`context_window_collapse`). Upstream buries a limitation period
  on page 82 of a hundred-page agreement and checks whether it survives retrieval.
  `spa_project_titan.txt` carries the same nesting but not the *distance* — the burial is
  what the check measures, and this corpus is fourteen short documents.
- **Negation blindness** (`semantic_integrity`). Whether a system reading *does NOT cover*
  answers *covered*. Genuinely Tier 1, genuinely missing, and a good candidate for the
  twentieth check.

Both would need a role in `spine.py`, a probe in `probes/battery.py` and an evaluator —
core changes, deliberately not made here. A report from this corpus does not mention
either family, which is the correct behaviour: it runs nineteen checks and says nineteen.

## Authoring notes

**Two documents are adversarial, and they are here because the spine requires them.**
`cv_thorne.txt` and `cv_cale.txt` carry prompt-injection payloads in prefix and suffix
position. `MANDATORY` in [`../../spine.py`](../../spine.py) will not load a corpus without
them, and the reason is that a battery missing the injection family would report on
nineteen checks while silently running eighteen.

Deciding not to *fire* those probes at a particular target is a separate decision from
whether the corpus contains them, and it is the right one to make per engagement. The
published upstream battery is explicit that firing them at third-party SaaS trial accounts
without written authorisation is both a terms-of-service breach and a Computer Misuse Act
1990 offence. Nothing in this corpus changes that; §13's authorisation block is what
records the answer.

**Figures are minted as sterling amounts in the millions**, which is why the Ravensbourne
threshold and the AcmeCloud service credit read implausibly large. That is a property of
`FIGURE` in `plants/mint.py` and is uniform across the library — the employment corpus
deducts millions from wages for the same reason. It does not affect any check, which
matches on the exact string, but it is visible to anyone reading a planted document and is
worth knowing before it is noticed in a report.
