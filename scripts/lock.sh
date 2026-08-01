#!/usr/bin/env bash
#
# Regenerate the dependency lockfiles.
#
# Edit requirements/*.in, run this, commit both. Never hand-edit requirements/*.txt.
#
# Why lockfiles at all: the report claims a third party can reconstruct the run from the
# manifest and the repository at a signed commit (NF11). That is false if the dependency
# set is a range, because "sentence-transformers>=2.2.2" resolves to different software
# in March than in August and a Tier 2 threshold means nothing without the model and
# library version behind it. Ranges also make `pip-audit` a statement about the day you
# installed rather than about the artefact.
#
# --universal resolves for every supported platform at once and encodes the differences
# as environment markers, so one file installs correctly on macOS arm64 and Linux x86_64.
# Resolving per-platform would produce lockfiles that silently disagree.
#
# --generate-hashes fixes the bytes, not only the version number. With --require-hashes
# at install time, a compromised or substituted artefact fails the install rather than
# reaching the run.

set -euo pipefail

cd "$(dirname "$0")/.."

# Lowest supported interpreter, so markers cover everything above it.
PYTHON_VERSION="3.11"

if command -v uv >/dev/null 2>&1; then
    UV="uv"
elif [ -x ".venv/bin/uv" ]; then
    UV=".venv/bin/uv"
else
    echo "uv not found. Install it with: pip install uv" >&2
    exit 1
fi

for layer in generate score dev; do
    echo "==> requirements/${layer}.txt"
    "${UV}" pip compile \
        --universal \
        --generate-hashes \
        --python-version "${PYTHON_VERSION}" \
        --no-header \
        "requirements/${layer}.in" \
        -o "requirements/${layer}.txt"
done

echo
echo "==> pyproject.toml pins must match the lockfiles"
python3 scripts/check_pins.py

echo
echo "Done. Commit requirements/*.in and requirements/*.txt together."
echo "Then re-run: python3 -m pytest tests/test_dependency_pinning.py"
