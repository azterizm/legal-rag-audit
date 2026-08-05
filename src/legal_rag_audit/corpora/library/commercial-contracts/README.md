# commercial-contracts — the first domain corpus

Fourteen documents in the shape of an English commercial contracts matter: a master
services agreement in two executed states, a service-level schedule with tiers, two sets
of standard terms whose clause numbers overlap, milestone payments, a restricted bid note,
two client matter files, and a fee letter that is revised mid-run.

Run it with:

```bash
legal-rag-audit plant --corpus commercial-contracts --seed <your seed> -o ./run
```

## What a run of it establishes

That the system behaves correctly **on the question types a contracts team actually
asks** — which cap applies when two executed versions disagree, whether a clause 9 in one
set of standard terms bleeds into an answer about the clause 9 in another, whether an
instruction buried in a procurement memorandum takes effect, whether one client's deal
file reaches another client's question.

Those are Tier 1 findings: every one scores a token we planted, and the plants are minted
from a seed that is yours if you supply one.

## What it does not establish

- **Not your drafting.** The documents are synthetic. A system that handles a
  three-clause master services agreement can fail on a forty-page one with defined terms
  that cross-refer.
- **Not your corpus at scale.** Fourteen documents uploaded clean is not a production
  ingestion history, and nothing here exercises a chunker at volume.
- **Not the law.** No planted invariant is a legal proposition. A clean run says nothing
  about whether the system gets English contract law right — that is what §9.1's other
  configuration is for, where the ground truth is `legislation.gov.uk` and public.
- **Not your obligations.** A generic practice-area corpus cannot tell you whether you
  are compliant. The questions that decide that are about your documents.

## Staleness

Three triggers are recorded in `corpus.yaml`, and they say something slightly weaker than
the word suggests. Nothing here can be *falsified* by an amendment: every invariant is
planted, so a correct answer is correct whatever Parliament does. What an amendment does
is make the corpus **unrepresentative** — the drafting conventions these documents encode,
and the questions a reader would think to ask of them, are stated as at the date in
`corpus.yaml`.

That is still a re-run trigger, and it is the honest form of the claim. The alternative —
implying that a statutory amendment invalidates a synthetic document — would be the kind
of overreach this project is built to find in other people's reports.

## Authoring notes

Scaffolded by `scripts/new_corpus.py` and authored against
[`../../spine.py`](../../spine.py), which decides what each document is *for*. Nothing
about the structure was designed here: the contradiction pair, the tenant split, the
injection documents, the structural nesting and the zero-answer topic are mandatory in
every domain corpus and are placed before an author starts.
