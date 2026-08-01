# Single image, carrying the score dependency set.
#
# Phase B splits this into Dockerfile.generate (five pure-Python libraries) and
# Dockerfile.score (adds the ML stack), per V2_FULL_PLAN.md §5.3. Until then this image
# carries everything and is not what a target should be asked to run.
#
# TODO(B2): pin the base image by digest (python:3.11-slim@sha256:...) and sign the built
# image with cosign. A tag is mutable, so it is a pin in name only.
FROM python:3.11-slim

WORKDIR /app

# Dependencies first, from the hash-pinned lockfile. --require-hashes means a substituted
# or tampered artefact fails the build rather than reaching a run: the version is fixed,
# and so are the bytes. Regenerate with scripts/lock.sh.
COPY requirements/score.txt ./requirements/score.txt
RUN pip install --no-cache-dir --require-hashes -r requirements/score.txt

# Source afterwards, so a code change does not invalidate the dependency layer.
# .dockerignore keeps internal_experiments/, secrets and run output out of the context.
COPY . .

# --no-deps: the lockfile above is the single source of installed versions. Without it
# pip re-resolves from pyproject.toml and could quietly install something else.
RUN pip install --no-cache-dir --no-deps -e .

# Non-root, per §12.3. Read-only rootfs, dropped capabilities and egress denial are
# supplied at run time; see the invocation in the README.
RUN useradd --system --uid 65532 --no-create-home auditor \
    && mkdir -p /output \
    && chown auditor:auditor /output
USER 65532:65532

VOLUME ["/output"]

ENTRYPOINT ["legal-rag-audit"]
