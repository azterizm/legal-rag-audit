# The corpus library

What a corpus is, what ships, what every corpus must contain, and the existing-corpus half
that needs no upload endpoint at all.

A run against the bundled demo corpus is **a demonstration, not an audit** — the reasons
are below and they are not small print.

---

A corpus is an artefact on disk, not code: a `corpus.yaml` and a directory of documents
with `@@plant-id@@` where each invariant goes. Three ship with this build.

```bash
legal-rag-audit plant --list-corpora
legal-rag-audit plant --corpus employment --seed <your seed> -o run/
```

| Corpus | Domain | What it is |
|---|---|---|
| `bundled-demo` | none | The try-it corpus. Published seed, synthetic prose, no practice area |
| `commercial-contracts` | supply, services, procurement (E&W) | A practice-area corpus |
| `employment` | contracts, policies, tribunal work (E&W) | A practice-area corpus |

Each ships a README saying what a run of it does **not** establish. Read that before
quoting a number from one anywhere.

**What does not vary.** Every corpus fills the same roles, declared once in
`corpora/spine.py`: the same fifteen documents in the same states, the same 29 invariants
with the same kinds, the same nineteen probes scored by the same checks. A corpus that
omits a role, invents one, or leaves one without a recorded location **does not load**, and
the refusal names what to write. That is what makes §9.5's contradiction pair, tenant
split, injection document, structural nesting and zero-answer topic *mandatory* rather
than merely recommended: they are not an author's to leave out.

**What varies.** The prose, the filenames, how a reader names each document, where in each
document an invariant sits, and the wording of each question — because *what is the
aggregate liability limit in the supplier agreement* retrieves nothing from an employment
index. Plus two judgment calls the loader cannot make for you: what would make the corpus
stale, and which authority a model reliably knows that no document here mentions.

Scaffold a new one with `python3 scripts/new_corpus.py <name>`. It arrives complete except
for the prose, and refuses to load until every `TODO` is gone.
[`authoring-a-corpus.md`](authoring-a-corpus.md) is the method.

## The bundled demo

`plant` with no `--corpus` writes a 15-document corpus from 14 documents plus one
revision, with 29 invariants inserted at declared locations. It is **a demo, not an
audit.** It measures whether a pipeline has generic properties on a best case: fifteen
short synthetic documents uploaded and queried immediately. It is not your production
ingestion history, not your chunking at 40,000 documents, not your index at scale, and not
your practice area. **A system can pass this run cleanly and fail badly in production.** A
generic corpus cannot tell you whether you are compliant, and this README will not pretend
otherwise.

| Documents | What they exercise |
|---|---|
| 2 tenant-isolated matter files, 3 invariant types in one | Cross-tenant leakage |
| 2 documents carrying a side-effect payload | Injection resistance |
| 2 near-identical supplier agreements with contradictory caps | Contradiction surfacing, latency |
| 1 nested service schedule with a leaf four levels under its heading | Structural integrity |
| 2 statutes with overlapping article numbers | Retrieval disambiguation, attribution |
| 1 settlement schedule with paired counterparties | Entity masking re-hydration |
| 1 namespace-scoped note | Routing contamination |
| 1 digest of authorities | Citation integrity |
| 1 chronology with three distinct referents | Context memory |
| 1 retainer notice, in two states | Index freshness |
| A question the corpus deliberately cannot answer | Parametric bleed, abstention |

Most documents carry **at least three invariants of at least two types**, because a system
that paraphrases a leaked clause still emits the counterparty name or the amount — those
are the payload, and a single planted string would be defeated by rewording. Five
documents carry fewer, and each records why beside itself in `corpora/spine.py`: in every
one, a second invariant would give the question a second correct answer, and a check that
cannot tell a right answer from a wrong one fails correct systems. A sixth appearing
without a recorded reason fails the build.

**What the collision guard checks**, and what it does not, goes into every ground-truth
manifest. It verifies that no value occurs in the corpus as authored, that no two plants
contain one another, that coined words are not in a bundled register of real parties, and
that every generated neutral citation carries a number above the range any division of the
High Court has issued in a year. It does **not** check the body of reported authority:
scoring is offline by construction, so no lookup leaves the machine, and the residue is
closed by manual review of the generated citations in the first corpus of each domain.

## Existing corpus — the half that needs no upload endpoint

Set `mode: existing`. There is no `path:`, because there is nothing to read: the corpus is
whatever the target already holds, and **`endpoints.upload` need not be in the config at
all**. That is the point rather than a convenience. Upload access is usually the friction
that turns a £500 engagement into a security review, so this half runs standalone.

```bash
legal-rag-audit plant --mode existing -o run/       # probes + answer key, no corpus
legal-rag-audit generate -c config.yaml --probes-in run/probes.jsonl -o responses.jsonl
```

What it gives up is everything planting buys — no canaries, no injection payloads, no
contradiction pairs. What it gives back is ground truth nobody has to take our word for,
and findings that cannot be dismissed as synthetic. [Verification runs
both](harness-verification.md); each covers the other's weakness.

Two checks live only here:

| Check | Ground truth | Needs |
|---|---|---|
| `point_in_time` | The phrase in force on a date, quoted from `legislation.gov.uk` under the Open Government Licence | `chat` |
| `licensed_content_reproduction` | A published set of publisher-assigned identifiers | `chat` |

**Point-in-time pairs ask the same provision at two moments, and the pair is the test.** A
single dated question measures almost nothing: a system that always answers with the
current law passes every question about the present. **Five anchors ship, ten readings** —
three Employment Rights Act 1996 provisions (the compensatory award cap under s.124, the
week's-pay maximum under s.227, and the insolvency weekly limit under s.186) and two
Companies Act 2006 accounting thresholds (small companies under s.382, medium-sized under
s.465).

Each phrase is chosen so it appears in one version of that provision and no other, so it
cannot be reached by a paraphrase of the other version, and so it has one written form —
a correct system that writes *£28* where the statute says *£28.00* must not be recorded as
having returned the superseded law. An answer carrying **both** versions passes; telling a
reader what the law was and what it became is more than was asked for, not less.

**The fourth rule excludes prose, and that cost an anchor.** A sixth anchor asked for the
unfair-dismissal qualifying period under s.108, whose answer the statute states in words:
*not less than one year*. Three systems wrote it three ways — the statutory phrase, *at
least one year*, and *one year of continuous employment* — and two of them were recorded as
having returned neither version of the law while having the law entirely right. A reading
may carry other accepted written forms of the same answer, and that feature is kept; what
it cannot do is close a set that has no closed form. Figures have one written form and
durations in English do not, so `era-108` was retired rather than widened a third time.

All ten readings now sit in closed validity ranges and can never change again. **That is a
gap, not an achievement**: the retired anchor was the only one asking for the law as it
stands, which is the more natural question and the only kind that can go stale. A
replacement wants a provision whose *current* value is a figure.

**Refreshing them is a command, not a diary note:**

```bash
legal-rag-audit ingest --strict -o run/statutes.json
```

It fetches each anchored provision as it stood on its date and confirms the phrase is
still there. Scoring never touches it — the anchors are committed and the battery runs
offline — so what this catches is an anchor going stale. With every reading now frozen,
what would move is not the law but the source: `legislation.gov.uk` revises its own
historic snapshots, and a phrase can stop matching without anything having been amended.
**Storage footprint: 3.3 kB across the ten snapshots**, because the store keeps a window
around each phrase rather than the statute.

**Licensed content is the question procurement already asks**, and the check is built so
it can never become an accusation. Only publisher-assigned *identifiers* are matched —
never editorial prose, which would mean storing a publisher's headnotes in order to ask
whether somebody else is storing them. A marker in the retrieval is the finding; a marker
cited to the publisher's own service passes as `external_fetch`; a marker with no evidence
either way is `NOT_CAPTURED`. The finding says content whose licence sits between them and
the publisher is being served from their index — never that anyone is infringing.

Both probes name **England and Wales**, and that is load-bearing rather than decorative.
The marker set is a set of *English* publisher identifiers, so a product holding French and
EU sources alongside UK ones, asked an unqualified question, answers on French law and
passes on an answer no marker could ever have appeared in. The check would then mean one
thing against one target and something else against the next, which defeats the purpose of
running a single battery across several.

## The corpus is checked before anything is sent

The corpus is resolved and verified before the first request goes out, and a problem with
it **aborts the run with a diagnosis and writes no report** (exit code 2). Checked:

- A planted root has a `base/` directory. A flat directory is refused rather than read as
  one, because reading it that way would silently drop the revision phase and take index
  freshness with it.
- `mode: existing` — nothing is checked, because nothing is read. The corpus is the
  target's own index and no local documents are involved.
- A run with documents to upload and no `endpoints.upload` aborts naming the three ways
  out, because they mean different things: probe their index, assume they hold the
  corpus, or declare somewhere to send it.
- Every document is UTF-8 and non-empty. Hidden files are skipped.
- Document order is sorted, not filesystem order, so the same corpus reads the same way
  on every machine.
- Every template slot is filled and every declared plant is inserted. A plant in the
  answer key and not in the corpus would fail a correct system.

This exists because the failure it replaces was silent. With the corpus missing, the
runner used to substitute two stand-in documents and *finish*: the report described a
2-document corpus while the config said more, and nothing on the page disclosed the
substitution. A setup problem must never render as a finding (NF9) — if the corpus cannot
be verified, there is no run.
