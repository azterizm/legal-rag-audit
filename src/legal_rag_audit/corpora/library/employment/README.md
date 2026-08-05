# employment — the second domain corpus

Fourteen documents in the shape of an English employment matter: a contract of employment
in two states, a company sick pay scheme with entitlement bands, two sets of works rules
whose rule numbers overlap, settlement payments, a restricted redundancy planning note,
two client grievance files, and a fee letter that is revised mid-run.

```bash
legal-rag-audit plant --corpus employment --seed <your seed> -o ./run
```

## What a run of it establishes

That the system behaves correctly on the questions an employment team asks — which cap
applies when a contract has been varied, whether rule 5 of one set of works rules bleeds
into an answer about rule 5 of another, whether an instruction buried in an HR policy memo
takes effect, whether one employer's grievance file reaches another employer's question.
Every finding scores a planted token.

## What it does not establish

The same four things as every corpus here, and they are worth reading rather than
assumed:

- **Not your drafting.** These contracts are three clauses long.
- **Not your corpus at scale.** Fourteen clean documents is not an ingestion history.
- **Not the law.** No planted invariant is a legal proposition. For employment law
  specifically, that gap is covered by the *other* configuration: `plant --mode existing`
  runs point-in-time pairs against `legislation.gov.uk`, and both its anchors are
  Employment Rights Act 1996 provisions. Run both.
- **Not your obligations.** A practice-area corpus cannot tell you whether you are
  compliant.

## Staleness

Three triggers in `corpus.yaml`. As in `commercial-contracts`, they date the corpus rather
than falsify it — every invariant is planted, so an amendment cannot make a correct answer
wrong. What it does is make the drafting unrepresentative.

## Authoring notes

This corpus is §9.5's acceptance test: *authoring a second domain corpus from the template
is timed and comes in under half a day.* It was scaffolded with `scripts/new_corpus.py
employment`, authored against the same spine as the first, and the elapsed time is recorded
in `V2_PROGRESS.md`.

Nothing here was designed. The scaffold arrives with every document, every slot and every
probe already placed; what an author adds is prose, question wording, the staleness
triggers and the out-of-corpus authority. The last two are the only judgment calls, and
they are the two the loader cannot make.
