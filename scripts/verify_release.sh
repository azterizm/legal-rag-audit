#!/usr/bin/env bash
#
# Verify a release without trusting anyone who wrote it.
#
#     ./scripts/verify_release.sh v0.2.0
#
# Signing artefacts is worth nothing on its own — it is a claim like any other until
# someone checks it, and almost nobody checks a signature they have to work out how to
# check. This is the other half of .github/workflows/release.yml: the same four
# properties, from the reader's side, in one command.
#
#   1. The tag is signed by the key committed at .github/release-signing-key.asc.
#   2. Each file matches its SHA-256 in SHA256SUMS.
#   3. Each file carries a cosign signature, recorded in the public Rekor transparency
#      log, made by this repository's release workflow.
#   4. Each file carries SLSA build provenance issued by GitHub's OIDC identity — a
#      signed statement that these bytes came out of that workflow at that commit.
#   5. Each container image named in IMAGES carries both, by digest.
#
# Step 5 depends on the four above rather than standing beside them: IMAGES is the file
# that maps this tag to two image digests, and it is checksummed, signed and attested
# with everything else. So by the time it is read, the mapping itself has been verified
# — which is the part a registry lookup alone cannot give you, because the registry is
# run by the same people who published the release.
#
# What none of this establishes: that the software does what the README says. It
# establishes only that what you downloaded is what the public workflow built from the
# public commit. That is the question signing can answer; the rest is what the tests,
# the gates and the report's own limits section are for.
#
# Requires: git, gpg, sha256sum (or shasum), and — for 3, 4 and 5 — cosign and gh.
# Those steps are skipped with a warning if their tool is absent, never silently.

set -euo pipefail

TAG="${1:-}"
REPO="${LEGAL_RAG_AUDIT_REPO:-azterizm/legal-audit-rag}"
WORKDIR="${2:-}"

if [ -z "${TAG}" ]; then
    echo "usage: $0 <tag> [directory-with-downloaded-artefacts]" >&2
    echo "example: $0 v0.2.0" >&2
    exit 2
fi

cd "$(dirname "$0")/.."

pass()  { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
fail()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
skip()  { printf '  \033[33mSKIP\033[0m  %s\n' "$1"; SKIPPED=$((SKIPPED + 1)); }

FAILURES=0
SKIPPED=0

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# ---------------------------------------------------------------- 1. the tag signature

echo
echo "1. Tag signature — who published this"
echo

KEY_FILE=".github/release-signing-key.asc"
if [ ! -f "${KEY_FILE}" ]; then
    fail "${KEY_FILE} is missing; without it there is nothing to verify against"
else
    FINGERPRINT=$(gpg --show-keys --with-colons "${KEY_FILE}" \
        | awk -F: '/^fpr:/ {print $10; exit}')
    pass "release key present: ${FINGERPRINT}"

    # Imported into a scratch keyring, so verifying a release cannot quietly add a key
    # to the reader's own trust store. A verification step with a side effect on the
    # machine running it is not one people should be asked to run.
    GNUPGHOME_TMP=$(mktemp -d)
    trap 'rm -rf "${GNUPGHOME_TMP}"' EXIT
    export GNUPGHOME="${GNUPGHOME_TMP}"
    chmod 700 "${GNUPGHOME_TMP}"
    gpg --quiet --import "${KEY_FILE}"

    if ! git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
        fail "tag ${TAG} is not in this clone — run: git fetch --tags"
    elif [ "$(git cat-file -t "${TAG}")" != "tag" ]; then
        fail "${TAG} is a lightweight tag, so it carries no signature"
    elif git verify-tag --raw "${TAG}" 2>&1 | grep -q 'GOODSIG'; then
        pass "tag ${TAG} is signed by that key"
        COMMIT=$(git rev-parse "${TAG}^{commit}")
        if git verify-commit --raw "${COMMIT}" 2>&1 | grep -q 'GOODSIG'; then
            pass "the tagged commit ${COMMIT:0:12} is signed by that key"
        else
            fail "the tagged commit ${COMMIT:0:12} is not signed"
        fi
    else
        fail "tag ${TAG} does not verify against ${KEY_FILE}"
    fi
    unset GNUPGHOME
fi

# ---------------------------------------------------------------------- the artefacts

# A failed tag signature is the end of the exercise. Downloading and checksumming
# artefacts from a release whose provenance is already in doubt would produce three
# more green ticks and a misleading impression.
if [ "${FAILURES}" -gt 0 ]; then
    echo
    echo "FAILED: the tag signature did not verify, so nothing below would mean"
    echo "anything. Do not install this. See SECURITY.md."
    exit 1
fi

if [ -z "${WORKDIR}" ]; then
    WORKDIR=$(mktemp -d)
    echo
    echo "Downloading ${TAG} artefacts to ${WORKDIR}"
    if command -v gh >/dev/null 2>&1; then
        gh release download "${TAG}" --repo "${REPO}" --dir "${WORKDIR}" --clobber
    else
        echo "  gh is not installed. Download the release assets yourself and re-run:" >&2
        echo "      $0 ${TAG} /path/to/artefacts" >&2
        exit 2
    fi
fi

# ------------------------------------------------------------------------ 2. checksums

echo
echo "2. Checksums — is this the same file"
echo

if [ ! -f "${WORKDIR}/SHA256SUMS" ]; then
    fail "SHA256SUMS is not in ${WORKDIR}"
else
    while read -r expected name; do
        [ -z "${name}" ] && continue
        name="${name#\*}"
        if [ ! -f "${WORKDIR}/${name}" ]; then
            fail "${name} listed in SHA256SUMS but not downloaded"
        elif [ "$(sha256 "${WORKDIR}/${name}")" = "${expected}" ]; then
            pass "${name}"
        else
            fail "${name} does not match its recorded SHA-256"
        fi
    done < "${WORKDIR}/SHA256SUMS"
fi

# --------------------------------------------------------------- 3. cosign signatures

echo
echo "3. Cosign signatures — logged in the public Rekor transparency log"
echo

if ! command -v cosign >/dev/null 2>&1; then
    skip "cosign is not installed — https://github.com/sigstore/cosign"
else
    # The identity is the workflow, not a key. Anyone who could produce this signature
    # had to do it from a run of release.yml in this repository, and the certificate
    # says so; a signature made anywhere else fails these two constraints.
    IDENTITY="https://github.com/${REPO}/.github/workflows/release.yml@refs/tags/${TAG}"
    for artefact in "${WORKDIR}"/*; do
        case "${artefact}" in
            *.sig|*.pem|*SHA256SUMS) continue ;;
        esac
        name=$(basename "${artefact}")
        if [ ! -f "${artefact}.sig" ] || [ ! -f "${artefact}.pem" ]; then
            fail "${name} has no cosign signature"
            continue
        fi
        if cosign verify-blob \
            --certificate "${artefact}.pem" \
            --signature "${artefact}.sig" \
            --certificate-identity "${IDENTITY}" \
            --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
            "${artefact}" >/dev/null 2>&1; then
            pass "${name}"
        else
            fail "${name} — signature does not verify for ${IDENTITY}"
        fi
    done
fi

# ------------------------------------------------------------------- 4. SLSA provenance

echo
echo "4. Build provenance — these bytes came out of that workflow"
echo

if ! command -v gh >/dev/null 2>&1; then
    skip "gh is not installed — https://cli.github.com"
else
    for artefact in "${WORKDIR}"/*; do
        case "${artefact}" in
            *.sig|*.pem|*SHA256SUMS) continue ;;
        esac
        name=$(basename "${artefact}")
        if gh attestation verify "${artefact}" --repo "${REPO}" >/dev/null 2>&1; then
            pass "${name}"
        else
            fail "${name} — no valid SLSA provenance attestation"
        fi
    done
fi

# --------------------------------------------------------------------- 5. the images

echo
echo "5. Container images — signed and attested by digest"
echo

if [ ! -f "${WORKDIR}/IMAGES" ]; then
    skip "this release published no IMAGES file, so it published no container images"
elif ! command -v cosign >/dev/null 2>&1; then
    skip "cosign is not installed — https://github.com/sigstore/cosign"
else
    IDENTITY="https://github.com/${REPO}/.github/workflows/release.yml@refs/tags/${TAG}"
    while read -r ref; do
        case "${ref}" in ''|\#*) continue ;; esac

        # A reference without a digest is not something to verify — it is a name, and
        # a name can be moved to point at other bytes after this file was written. If
        # one appears here, the release is malformed and saying so is the answer.
        case "${ref}" in
            *@sha256:*) ;;
            *) fail "${ref} is a tag, not a digest — nothing signed can be checked against it"
               continue ;;
        esac

        if cosign verify "${ref}" \
            --certificate-identity "${IDENTITY}" \
            --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
            >/dev/null 2>&1; then
            pass "cosign  ${ref}"
        else
            fail "cosign  ${ref} — no signature for ${IDENTITY}"
        fi

        if ! command -v gh >/dev/null 2>&1; then
            skip "provenance ${ref} — gh is not installed"
        elif gh attestation verify "oci://${ref}" --repo "${REPO}" >/dev/null 2>&1; then
            pass "provenance  ${ref}"
        else
            fail "provenance  ${ref} — no valid SLSA attestation"
        fi
    done < "${WORKDIR}/IMAGES"
fi

# ----------------------------------------------------------------------------- verdict

echo
if [ "${FAILURES}" -gt 0 ]; then
    echo "FAILED: ${FAILURES} check(s) did not pass. Do not install this."
    echo "If you believe the release is genuine, report it: see SECURITY.md."
    exit 1
fi

if [ "${SKIPPED}" -gt 0 ]; then
    echo "PASSED, with ${SKIPPED} check(s) skipped for missing tooling."
    echo "A skipped check established nothing. Install cosign and gh for the full set."
    exit 0
fi

echo "PASSED: every check. What you have is what the public workflow built from"
echo "the signed commit. That is all signing can tell you — see SECURITY.md."
