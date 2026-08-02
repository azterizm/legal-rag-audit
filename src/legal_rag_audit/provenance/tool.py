"""Which build produced this report, and whether its commit carries a signature.

§6.5 asks for `tool_version` and `tool_commit_sha`, GPG-signed. The signature is the
one place in this project where commit signing does work rather than decorate a trust
page: a report claims to have been produced by a specific, inspectable revision, and
the signature is what makes that claim checkable by someone who has the repository
and does not have us.

**This module reports whether a signature is present. It does not verify it**, and
that is deliberate on two grounds.

The first is the offline guarantee. Verification means `git log --pretty=%G?`, which
invokes gpg in a child process, and a gpg configured with `auto-key-retrieve` will
fetch a missing key from a keyserver. `score` runs inside `offline()`, which patches
*this* process's sockets and cannot see a child's — so a verifying manifest would
carry a network path the enforcement does not cover, on the one claim (§5.1, F18) the
project makes most loudly. Reading the commit object's `gpgsig` header touches no
network and needs no gpg at all.

The second is that self-attestation is worth nothing. "We checked our own signature
and it was fine" is not evidence to a reader who is deciding whether to trust us. So
the manifest records presence, the sha, and the exact command a sceptic runs to verify
it themselves — which is the only form of this claim that survives being doubted.

Everything here degrades to an explicit "unavailable, and here is why". A report from
an installed wheel outside a checkout legitimately has no commit sha, and recording
`null` with a reason is a different statement from omitting the field — the same
distinction NOT_CAPTURED draws for checks (F40).
"""

import subprocess
from pathlib import Path
from typing import Any, Optional

#: Where to ask git about. The *package* directory, never the process working
#: directory: someone running `score` from inside their own repository must not have
#: their commit recorded as the provenance of our tool.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

_TIMEOUT_SECONDS = 5


def tool_version() -> str:
    from .. import __version__

    return __version__


def _git(*args: str) -> Optional[str]:
    """Run a git command against the package directory, or return None.

    Only commands that read local objects are used here — `rev-parse`, `cat-file`,
    `status`. None of them opens a socket or invokes gpg, which is what makes it safe
    to call from inside `score`'s offline enforcement. Every failure mode (no git, no
    checkout, a timeout) is the same answer: we do not know.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_PACKAGE_ROOT,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def tool_commit() -> dict[str, Any]:
    """The revision that produced this run, as far as it can be established."""
    def unknown(reason: str) -> dict[str, Any]:
        return {
            "sha": None,
            "signature": None,
            "verify_with": None,
            "working_tree": None,
            "unavailable": reason,
        }

    if _git("rev-parse", "--is-inside-work-tree") != "true":
        return unknown(
            "not running from a git checkout — the commit cannot be established "
            "from an installed package. Reproduce from the version instead."
        )

    sha = _git("rev-parse", "HEAD")
    if not sha:
        return unknown("a git checkout with no commits")

    # The raw commit object. A signed commit carries a `gpgsig` header; reading it is
    # a local object read, where verifying it is a gpg invocation. See the module
    # docstring for why this side of that line.
    commit_object = _git("cat-file", "commit", sha) or ""
    header = commit_object.split("\n\n", 1)[0]
    signed = any(
        line.startswith(("gpgsig ", "gpgsig-sha256 ")) for line in header.split("\n")
    )

    # Uncommitted changes mean the sha does not describe the code that ran. Saying so
    # is the difference between a reproducible artefact and one that merely looks it.
    working_tree = "modified" if _git("status", "--porcelain") else "clean"

    return {
        "sha": sha,
        "signature": "present" if signed else "absent",
        "verify_with": f"git verify-commit {sha}" if signed else None,
        "working_tree": working_tree,
        "unavailable": None,
    }


def tool_provenance() -> dict[str, Any]:
    commit = tool_commit()
    return {
        "version": tool_version(),
        "commit_sha": commit["sha"],
        "commit_signature": commit["signature"],
        "commit_signature_verify_with": commit["verify_with"],
        "working_tree": commit["working_tree"],
        "commit_unavailable": commit["unavailable"],
    }
