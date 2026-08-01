"""Make `score` unable to open a socket (F18, §5.1).

The claim is *"scoring never contacts anything"*. A comment asserting that is worth
nothing to a reviewer; a process that raises on `socket()` is checkable in a few
seconds, which is the whole point — the review surface shrinks instead of the promise
growing.

Two layers, because they fail differently:

* This module, which makes an attempt raise inside our own process. It survives being
  run from a laptop with a working network, which is where scoring actually happens.
* `docker run --network=none`, documented in the README. It survives us being wrong
  about which library reaches the network and how.

Neither substitutes for the other. This one turns a leak into a stack trace at our desk;
the container turns it into an impossibility on someone else's.
"""

import socket
from contextlib import contextmanager
from typing import Any, Iterator

#: Set once enforcement is on, so a second call is a no-op rather than a wrapper
#: around a wrapper.
_ENFORCED = False

_ORIGINALS: dict[str, Any] = {}

_MESSAGE = (
    "Scoring attempted a network connection.\n"
    "  `score` runs offline by construction (V2_FULL_PLAN.md §5.1, F18): it reads a\n"
    "  response file and a ground-truth manifest, and reaches nothing else.\n"
    "  This is a defect in the harness, not a finding about the target.\n"
    "  The usual cause is a Tier 2 model that is not in the local cache — pre-fetch it\n"
    "  and record the version in the manifest, so the run is reproducible rather than\n"
    "  dependent on what the model hub served that day."
)


class OfflineViolation(RuntimeError):
    """Scoring tried to open a socket. Aborts the run; never becomes a finding."""


def _refuse(*_args: Any, **_kwargs: Any) -> Any:
    raise OfflineViolation(_MESSAGE)


class _RefusingSocket:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise OfflineViolation(_MESSAGE)


def enforce_offline() -> None:
    """Replace the socket factory and the two functions that bypass it.

    `socket.socket` alone is not enough: `create_connection` and `getaddrinfo` are
    reachable independently, and a name lookup that succeeds tells a resolver — and
    anyone watching it — which host we were about to contact. Blocking the lookup keeps
    the claim true at the DNS layer too.
    """
    global _ENFORCED
    if _ENFORCED:
        return

    _ORIGINALS["socket"] = socket.socket
    _ORIGINALS["create_connection"] = socket.create_connection
    _ORIGINALS["getaddrinfo"] = socket.getaddrinfo

    socket.socket = _RefusingSocket  # type: ignore[assignment,misc]
    socket.create_connection = _refuse  # type: ignore[assignment]
    socket.getaddrinfo = _refuse  # type: ignore[assignment]
    _ENFORCED = True


def release_offline() -> None:
    """Undo enforcement. For tests only — nothing in the scoring path calls this."""
    global _ENFORCED
    if not _ENFORCED:
        return
    socket.socket = _ORIGINALS["socket"]
    socket.create_connection = _ORIGINALS["create_connection"]
    socket.getaddrinfo = _ORIGINALS["getaddrinfo"]
    _ORIGINALS.clear()
    _ENFORCED = False


@contextmanager
def offline() -> Iterator[None]:
    """Scoped enforcement, so a test can assert both that it bites and that it lifts."""
    already = _ENFORCED
    enforce_offline()
    try:
        yield
    finally:
        if not already:
            release_offline()


def is_enforced() -> bool:
    return _ENFORCED
