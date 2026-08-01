# internal_experiments — NOT part of the published tool

Everything under this directory is **excluded from the published wheel, the container
image, and every claim made about `legal-rag-audit`.**

It exists so that experimental work is kept somewhere legible rather than deleted and
half-remembered. Nothing here is installed, imported, tested, or shipped.

## Exclusion is enforced, not promised

| Boundary | Mechanism |
|---|---|
| Python wheel / sdist | `pyproject.toml` declares an explicit `packages = [...]` list. `internal_experiments` is not on it and is not a subpackage of `legal_rag_audit`. |
| Container image | `.dockerignore` excludes `internal_experiments/`. |
| Acceptance gate | `scripts/check_no_remote_scoring.sh` greps the published package for remote-scoring vendor markers and fails the build if any appear. This directory is the only permitted location. |
| Test gate | `tests/test_no_remote_scoring.py` asserts the same thing from pytest, including that no installed module reaches this code. |

## `remote_scoring/` — why it is here and not in the package

v1 shipped a `--use-gemini` flag that routed hallucination, retrieval-relevance and
confidence scoring through the Google Generative Language API. That path contradicted
two claims the tool made about itself:

1. **Determinism.** The hallucination path issued three generation calls per claim and
   averaged the scores. Same responses in, different report out.
2. **Zero data exfiltration.** The corpus text and the target's answers were transmitted
   to a third party, making that third party a sub-processor and each run a data-transfer
   event — on a tool whose stated selling point is that nothing leaves the environment.

The v2 decision (V2_FULL_PLAN.md §4.2) is that the shipped default carries no remote
scoring path at all, so both claims stand unqualified on the local path. The code is
retained here as a record and as a base for internal experiments.

## Conditions on ever using this again

If any of this is run, even once, on data that is not ours:

- The determinism and zero-exfiltration claims are **rescoped to the local path in the
  same paragraph** as they are made — never in a footnote.
- The run manifest records `remote_scoring: true`.
- Findings produced this way are segregated into Tier 2 and labelled with the model
  name, version and threshold.
- It does not enter the published code path to do any of the above.

## Loose scripts

`test_gemini_confidence.py` and `test_gemini_hallucination.py` were `test_`-prefixed
files at the repository root. They are not tests — they are manual scripts that require a
live API key and print to stdout. They are kept here, renamed, so pytest never collects
them.
