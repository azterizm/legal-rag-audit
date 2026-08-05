# Authoring a domain corpus

A corpus is the scarce asset in this project. The harness is given away on purpose — every
control that makes it safe to run also makes it worthless to hoard — and what is left is
the corpus library, the representation delta, and a named person attaching a dated
conclusion to a run.

So the economics that matter are the authoring cost, and the claim this document exists to
make good on is: **the second corpus in a practice area is a template edit, not a design
exercise.**

## The split

Two halves, and the line between them is the whole idea.

| | Where it lives | Who decides it |
|---|---|---|
| Which documents exist, and what each is for | `src/legal_rag_audit/corpora/spine.py` | Fixed. Not an author's to change |
| Which invariants each carries, and of what kind | the spine | Fixed |
| Which questions are asked, and which checks score them | `probes/battery.py` | Fixed |
| The prose of each document | `corpus.yaml` + `documents/` | The author |
| The wording of each question | `corpus.yaml` | The author |
| Where in each document an invariant sits | `corpus.yaml` | The author |
| What would make the corpus stale | `corpus.yaml` | The author |
| Which authority the model knows and the corpus does not mention | `corpus.yaml` | The author |

An author writes prose around slots somebody else placed. Nothing about the structure is
open, and that is not a restriction — it is the reason the work is bounded. A corpus that
varied its structure would score different checks under the same names, and two reports
from two corpora would not be comparable.

## The loop

```bash
python3 scripts/new_corpus.py employment
legal-rag-audit plant --corpus employment -o /tmp/check
```

The second command fails, and names one thing to fix. Fix it, run it again. When it
succeeds you have a corpus.

That is the whole method. The validator is the deliverable, not a safety net: an author
who discovers a missing plant when a live run produces a finding has discovered it in the
worst possible place, because a setup problem rendering as a finding is exactly what NF9
forbids.

Every refusal names the thing to write:

- a document key with no entry → *what it is for*, and the invariants it must carry
- a slot in the manifest with no `@@marker@@` in the body → the marker to write
- a marker in the body the spine does not declare → the invented id
- a slot with no location → the plant id, and why a location is not optional
- an unworded probe → the probe id
- a probe quoting the answer it is scored on → the plant it quoted
- an `out_of_corpus` phrase that turns out to be in a document → both, and why it matters
- any remaining `TODO` → the file it is in

## The two judgment calls

Everything else is scaffolded. These two are not, because only somebody who knows the
practice area can make them.

**`staleness_triggers`** — which instruments, if amended, reach this corpus. Say what they
reach and how to watch them. Note the register: a planted invariant cannot be *falsified*
by an amendment, because a correct answer is correct whatever Parliament does. What an
amendment does is make the corpus **unrepresentative** — the drafting these documents
encode, and the questions a reader would think to ask of them, are stated as at a date.
Write it that way. Implying that a statutory amendment invalidates a synthetic document is
the kind of overreach this project exists to find in other people's reports.

An empty list is a legitimate answer only for a corpus that states no legal position at
all. `bundled-demo` is the only one that qualifies. A test refuses an empty list on any
other.

**`out_of_corpus`** — an authority a base model reliably knows and no document here
mentions. Its appearance in an answer is evidence of the model's weights rather than of
retrieval, which is the whole of §8.2 #6. Pick one that is genuinely famous in the practice
area: `Carlill` for contracts, `Burchell` for unfair dismissal. The loader checks the
second half of the claim — that no document contains it — because a phrase that turned out
to be in the corpus would record a system quoting its own documents as having bled, and a
false positive is a release blocker.

## Writing the prose

Keep it thin. Every check scores a token, not a paragraph, so a document that tried to be
realistic drafting would make the battery harder to reason about without making any check
stronger. What the prose has to do is two things:

1. **Be retrievable.** A question has to have a lexical handle. The document needs the
   words somebody would search with.
2. **Be plausible in the practice area.** This is what a domain corpus is for. A supply
   agreement in an employment corpus tells you nothing about how the system handles
   employment questions.

Write questions the way a practitioner in that area would ask them. `{plant:<id>}` fills in
an identifier a question cannot retrieve without — a band name, a tier heading. It may
never name an expected answer, and the loader refuses one that does.

## Before you finish

Write the README. Every corpus in the library carries one, and the section that matters is
**what a run of it does not establish**. Be specific and be complete: the sentence a report
needs most is the one that says what it does not cover, and a corpus whose README is vague
about that will be quoted as though it covered everything.

Then bump `version` if you are changing a corpus that has been used in a run. The version
goes on the attestation and the digest goes in the run manifest, so two reports from two
versions of the same corpus can be told apart.
