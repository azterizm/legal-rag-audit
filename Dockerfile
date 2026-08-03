# Single image, carrying the score dependency set.
#
# Phase B splits this into Dockerfile.generate (five pure-Python libraries) and
# Dockerfile.score (adds the ML stack), per V2_FULL_PLAN.md §5.3. Until then this image
# carries everything and is not what a target should be asked to run.
#
# The base image is pinned by digest, not by tag. `python:3.11-slim` is a mutable
# pointer — the same defect as `actions/checkout@v7` in a workflow, and the same one
# `--require-hashes` exists to prevent one layer down. Pinning every Python dependency
# to its bytes and then building on top of whatever `3.11-slim` resolved to that morning
# would leave the whole chain resting on its weakest link.
#
# The trailing comment records which tag the digest was, so a bump is reviewable. Update
# both together:
#
#     docker buildx imagetools inspect python:3.11-slim
#
# Still outstanding, and deliberately last: the Dockerfile.generate / Dockerfile.score
# split (§5.3), publishing the images, and signing them with cosign. Image signing needs
# published images, so it ships in the same change as the split rather than before it.
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

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
