# Development

```bash
git clone https://github.com/azterizm/legal-rag-audit && cd legal-rag-audit
```

---

## Tests and acceptance gates

```bash
pip install --require-hashes -r requirements/dev.txt && pip install --no-deps -e .
pytest
```

Skip the tests that build a wheel or download a model with `pytest -m "not slow"`.

Acceptance gates:

```bash
./scripts/check_no_remote_scoring.sh
```

Asserts there is no remote-scoring vendor, credential or endpoint anywhere in
`src/legal_rag_audit/`, that no scoring code imports an HTTP client, that
`internal_experiments/` is excluded from both the wheel and the image, and that no claim
in a published document is made without its scope attached. That last check covers
`README.md`, `SECURITY.md`, `docs/threat-model.md`, `docs/responses-schema.md` and
`docs/harness-verification.md` — it was widened from the README alone in Phase B2, and
the first run over the new set found the schema document asserting *"nothing is sent
anywhere"* with no scope on it.

```bash
python3 -m pytest tests/test_reference_target.py -q
```

The two numbers of [§14.2](docs/harness-verification.md): sensitivity — every registered
check, given a target exhibiting the defect it looks for, reports it — and specificity —
a target behaving correctly produces no findings across three passes. Both run against a
reference server in `tests/mock_target/` over the real HTTP path, and both block a
release. The gate is written against the check register rather than a count, so shipping
an evaluator without a pathology profile fails the build instead of shrinking the
denominator.

```bash
python3 scripts/check_pins.py
```

Asserts every requirement is exact, every lockfile entry carries hashes, that
`pyproject.toml` agrees with the lockfiles, and that the base dependency set is the
`generate` layer and no more. Two sources of truth that disagree are worse than one that
is vague, because the disagreement is silent.

```bash
python3 scripts/gen_schemas.py --check
```

Asserts the published JSON Schemas still match the pydantic models that enforce them.
The schemas are generated, never hand-edited: a published contract that `score` would
reject is worse than none, because it sends someone away to build the wrong thing.

```bash
python3 scripts/gen_sbom.py --check
```

Asserts the committed SBOMs still describe the lockfiles. Same ratchet: a dependency bump
that forgets the SBOM leaves a published document describing software nobody installs.
Regenerating from an unchanged lockfile produces a byte-identical document — no
generation timestamp, and a serial number derived from the lockfile's own digest — which
is what makes a drift check possible at all.

Changing a dependency:

```bash
./scripts/lock.sh
```

Edit `requirements/*.in`, run that, commit the `.in` and `.txt` together, then regenerate
the SBOMs with `python3 scripts/gen_sbom.py`. Never hand-edit a lockfile — one that cannot
be regenerated is not a lockfile.

Cutting a release:

```bash
git tag -s v0.2.0 -m "v0.2.0" && git push origin v0.2.0
```

The tag must be signed and annotated. `release.yml` verifies the signature **before** it
builds anything — a pipeline that builds first has already spent its provenance on an
unverified commit — then attests, signs and publishes. Anyone can check the result with
`./scripts/verify_release.sh v0.2.0`.

`internal_experiments/` is not installed, not imported, not collected by pytest and not
copied into the image. Read `internal_experiments/README.md` before touching anything in
it.
