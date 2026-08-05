"""`score` cannot reach the network — enforced, and unreachable by construction (F18).

Two independent assertions, because they fail differently and either one alone would
leave the claim resting on trust.

The static one: no module reachable from `legal_rag_audit.score` imports the transport
package. Walked over the AST rather than by importing, so it holds for imports inside
functions too — the lazy ones the registry uses deliberately.

The dynamic one: with enforcement on, a socket attempt raises. That covers the case the
static walk cannot — a third-party library reaching out on its own, which is exactly how
a model download would happen at scoring time.

Neither replaces `docker run --network=none`. These fail at our desk; the container
fails on someone else's.
"""

import ast
import socket
from pathlib import Path

import pytest

from legal_rag_audit.score import score
from legal_rag_audit.score.offline import (
    OfflineViolation,
    is_enforced,
    offline,
)

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "legal_rag_audit"


def local_imports(path: Path, package: Path) -> set[str]:
    """Modules inside this package that `path` imports, at any nesting depth.

    Relative imports are resolved against the file's own position, so `..transport`
    from `score/run.py` resolves to `legal_rag_audit.transport` and is visible here
    even though nothing at module scope executes it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package_parts = path.relative_to(package.parent).parts[:-1]
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package_parts[: len(package_parts) - node.level + 1])
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module.startswith("legal_rag_audit"):
                found.add(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("legal_rag_audit"):
                    found.add(alias.name)
    return found


def module_path(dotted: str, package: Path) -> Path | None:
    relative = Path(*dotted.split(".")[1:])
    for candidate in (package / relative / "__init__.py", package / f"{relative}.py"):
        if candidate.exists():
            return candidate
    return None


def reachable_from(root: str, package: Path = PACKAGE) -> set[str]:
    seen: set[str] = set()
    queue = [root]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        path = module_path(current, package)
        if path is None:
            continue
        for imported in local_imports(path, package):
            if imported not in seen:
                queue.append(imported)
    return seen


def test_score_cannot_reach_the_transport_package():
    reachable = reachable_from("legal_rag_audit.score")
    offenders = {m for m in reachable if "transport" in m}
    assert not offenders, (
        f"score imports the transport package (directly or transitively): {offenders}. "
        f"The offline claim in §5.1 is a property of what the scorer can reach, not a "
        f"promise about how it is written."
    )


def test_score_cannot_reach_the_generate_package():
    reachable = reachable_from("legal_rag_audit.score")
    offenders = {m for m in reachable if m.startswith("legal_rag_audit.generate")}
    assert not offenders, f"score imports the generate package: {offenders}"


def test_the_walk_would_notice(tmp_path):
    """Negative control: the import walk finds a transport import when there is one.

    A structural test that cannot fail is worse than no test — it reports a property
    nobody checked.
    """
    fake = tmp_path / "legal_rag_audit" / "score"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text(
        "def f():\n    from ..transport import TargetClient\n", encoding="utf-8"
    )
    reachable = reachable_from(
        "legal_rag_audit.score", package=tmp_path / "legal_rag_audit"
    )
    assert "legal_rag_audit.transport" in reachable


# --------------------------------------------------------------------------- runtime


def test_a_socket_raises_while_enforced():
    with offline():
        with pytest.raises(OfflineViolation):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_create_connection_raises_while_enforced():
    with offline():
        with pytest.raises(OfflineViolation):
            socket.create_connection(("127.0.0.1", 9))


def test_name_resolution_raises_while_enforced():
    """A lookup that succeeds has already told a resolver where we were going."""
    with offline():
        with pytest.raises(OfflineViolation):
            socket.getaddrinfo("example.com", 443)


def test_the_message_says_it_is_our_defect_not_their_finding():
    with offline():
        with pytest.raises(OfflineViolation) as e:
            socket.socket()
    message = str(e.value)
    assert "not a finding about the target" in message
    assert "§5.1" in message


def test_enforcement_lifts_cleanly():
    assert not is_enforced()
    with offline():
        assert is_enforced()
    assert not is_enforced()
    # Still usable afterwards, or every test after this one would fail for the wrong
    # reason.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.close()


def test_enforcement_is_idempotent():
    with offline():
        with offline():
            assert is_enforced()
        assert is_enforced(), "the inner scope released enforcement the outer one owned"
    assert not is_enforced()


def test_score_does_not_leave_the_process_unable_to_open_a_socket(tmp_path):
    """Enforcement is scoped to the call, not to the process.

    It works by replacing attributes on the `socket` module, so leaving it on outlives
    the call that turned it on. In the CLI that is harmless — scoring is the whole
    process — but `score()` is also an importable function, and a caller who scores one
    file should not find networking permanently broken afterwards as a side effect.

    The claim being made is the accurate one: nothing reaches the network *while
    scoring runs*. This was found by running the suite together; every test passed in
    isolation.
    """
    from legal_rag_audit.interchange import (
        Response,
        write_ground_truth,
        write_probes,
        write_responses,
    )
    from legal_rag_audit.probes import build_ground_truth, build_probes

    probes = build_probes()
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "gt.json", build_ground_truth())
    write_responses(
        tmp_path / "responses.jsonl",
        [
            Response(run_id="r", probe_id=p.probe_id, query=p.text, answer="An answer.")
            for p in probes
        ],
    )

    assert not is_enforced()
    score(
        str(tmp_path / "responses.jsonl"),
        str(tmp_path / "gt.json"),
        str(tmp_path / "probes.jsonl"),
        skip_tier2=True,
    )
    assert not is_enforced(), "score() left enforcement on for the whole process"

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.close()


def test_scoring_a_real_file_runs_with_enforcement_on(tmp_path):
    """The end this all exists for: a genuine score() call, sockets blocked throughout."""
    from legal_rag_audit.interchange import (
        Response,
        write_ground_truth,
        write_probes,
        write_responses,
    )
    from legal_rag_audit.probes import build_ground_truth, build_probes

    probes = build_probes()
    write_probes(tmp_path / "probes.jsonl", probes)
    write_ground_truth(tmp_path / "gt.json", build_ground_truth())
    write_responses(
        tmp_path / "responses.jsonl",
        [
            Response(run_id="r", probe_id=p.probe_id, query=p.text, answer="An answer.")
            for p in probes
        ],
    )

    with offline():
        report = score(
            str(tmp_path / "responses.jsonl"),
            str(tmp_path / "gt.json"),
            str(tmp_path / "probes.jsonl"),
            enforce=False,  # the context manager already did it
            skip_tier2=True,
        )
    assert report["summary"]["checks_registered"] == 20
