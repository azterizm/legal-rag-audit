#!/usr/bin/env bash
#
# Phase A acceptance gate (V2_FULL_PLAN.md §4.2).
#
# Asserts that the published package contains no remote-scoring path: no third-party
# inference or embedding vendor, no vendor credential, no vendor endpoint.
#
# The plan states the gate as `grep -ri "gemini\|openai\|anthropic\|api_key" src/`.
# Two deliberate narrowings, both documented rather than silent:
#
#   1. `api_key` is excluded from the vendor pattern. The v2 config schema (§6.1)
#      mandates `auth.type: api_key` and `token_env: TARGET_API_KEY` for authenticating
#      to the *target*. That is the system under test, not a scoring sub-processor.
#      Vendor credential names (GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY) are
#      matched explicitly instead, so nothing is lost.
#   2. The package lives at `legal_rag_audit/`, not `src/legal_rag_audit/`. The src
#      layout move belongs to the Phase B package refactor.
#
# internal_experiments/ is the one permitted location and is excluded from the wheel
# (explicit `packages` list in pyproject.toml) and the image (.dockerignore).

set -uo pipefail

PACKAGE_DIR="legal_rag_audit"

VENDOR_PATTERN='gemini|openai|anthropic|generativelanguage|api\.openai\.com|GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|google\.generativeai|--use-gemini|use_gemini|allow_remote_scoring|allow-remote-scoring'

status=0

echo "==> Scanning ${PACKAGE_DIR}/ for remote-scoring vendor markers"
# -I skips binaries; stale .pyc files are build output, not source.
if hits=$(grep -rniIE --exclude-dir=__pycache__ "${VENDOR_PATTERN}" "${PACKAGE_DIR}" 2>/dev/null); then
    echo "FAIL: remote-scoring markers found in the published package:"
    echo "${hits}"
    status=1
else
    echo "  clean"
fi

echo "==> Checking the package declares no network-capable scoring dependency"
if hits=$(grep -rn "^import requests\|^from requests\|import requests$" "${PACKAGE_DIR}" 2>/dev/null); then
    echo "FAIL: 'requests' reached the package; scoring must not perform HTTP:"
    echo "${hits}"
    status=1
else
    echo "  clean"
fi

echo "==> Checking internal_experiments/ is excluded from the wheel"
packages_line=$(grep -E '^\s*packages\s*=' pyproject.toml 2>/dev/null || true)
if [ -z "${packages_line}" ]; then
    echo "FAIL: pyproject.toml has no explicit 'packages' list, so setuptools would"
    echo "      discover internal_experiments/ and ship it"
    status=1
elif echo "${packages_line}" | grep -q "internal_experiments"; then
    echo "FAIL: internal_experiments is on the packages list: ${packages_line}"
    status=1
else
    echo "  clean (explicit packages list, internal_experiments absent)"
fi

echo "==> Checking internal_experiments/ is excluded from the image"
if grep -q "^internal_experiments/" .dockerignore 2>/dev/null; then
    echo "  clean"
else
    echo "FAIL: .dockerignore does not exclude internal_experiments/"
    status=1
fi

echo "==> Checking README carries no unqualified determinism or exfiltration claim"
python3 scripts/check_readme_claims.py || status=1

if [ "${status}" -eq 0 ]; then
    echo
    echo "PASS: no remote-scoring path in the published artefacts."
else
    echo
    echo "FAIL: see above."
fi
exit "${status}"
