#!/usr/bin/env python3
"""Assert the dependency set is exactly pinned and internally consistent.

Three properties, all of which have to hold for NF11 (a third party reconstructs the run
from the manifest and the repository at a signed commit):

  1. Nothing is loose. Every requirement in pyproject.toml and every line in the
     lockfiles is `==`, not `>=` or `~=`.
  2. pyproject.toml and the lockfiles agree. Two sources of truth that disagree are worse
     than one that is vague, because the disagreement is silent.
  3. Every lockfile entry carries hashes. A pinned version fixes what you asked for; a
     hash fixes what you received.

Run via scripts/lock.sh, or directly.
"""

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_DIR = REPO_ROOT / "requirements"
LAYERS = ("generate", "score", "dev")

PIN_RE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s;\\]+)")
LOOSE_RE = re.compile(r"(>=|<=|~=|!=|\s>|\s<)")


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lockfile(path: Path) -> dict[str, set[str]]:
    """Map normalised package name -> set of pinned versions (markers may give several)."""
    pins: dict[str, set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--hash"):
            continue
        match = PIN_RE.match(stripped)
        if match:
            pins.setdefault(normalise(match.group(1)), set()).add(match.group(2))
    return pins


def lockfile_entries_with_hashes(path: Path) -> tuple[int, list[str]]:
    """Count pinned entries and return those with no --hash attached."""
    text = path.read_text(encoding="utf-8")
    # uv writes one logical requirement per backslash-continued block.
    blocks = re.split(r"\n(?=[A-Za-z0-9_.\-]+\s*==)", text)
    total, unhashed = 0, []
    for block in blocks:
        match = PIN_RE.match(block.strip())
        if not match:
            continue
        total += 1
        if "--hash=" not in block:
            unhashed.append(f"{match.group(1)}=={match.group(2)}")
    return total, unhashed


def main() -> int:
    failures: list[str] = []

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    declared: dict[str, str] = {}
    all_requirements = list(project.get("dependencies", []))
    for extra_reqs in project.get("optional-dependencies", {}).values():
        all_requirements.extend(extra_reqs)

    for requirement in all_requirements:
        match = PIN_RE.match(requirement.strip())
        if not match:
            failures.append(
                f"pyproject.toml: {requirement!r} is not an exact pin. Every dependency "
                f"must be '==' so the same software is installed everywhere."
            )
            continue
        declared[normalise(match.group(1))] = match.group(2)

    # 1 + 3: the lockfiles themselves.
    locks: dict[str, dict[str, set[str]]] = {}
    for layer in LAYERS:
        path = REQUIREMENTS_DIR / f"{layer}.txt"
        if not path.exists():
            failures.append(f"missing lockfile: {path.relative_to(REPO_ROOT)}")
            continue

        locks[layer] = parse_lockfile(path)

        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("--hash"):
                continue
            if PIN_RE.match(stripped):
                continue
            if LOOSE_RE.search(stripped) and not stripped.startswith(("-r", "-c")):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: loose specifier: {stripped}"
                )

        total, unhashed = lockfile_entries_with_hashes(path)
        if total == 0:
            failures.append(f"{path.relative_to(REPO_ROOT)}: no pinned requirements found")
        if unhashed:
            failures.append(
                f"{path.relative_to(REPO_ROOT)}: {len(unhashed)} entries carry no hash: "
                f"{', '.join(unhashed[:5])}"
            )

    # 2: pyproject agrees with the layer that owns each dependency.
    for name, version in declared.items():
        found_in = [layer for layer in LAYERS if name in locks.get(layer, {})]
        if not found_in:
            failures.append(
                f"pyproject.toml declares {name}=={version}, which appears in no "
                f"lockfile. Add it to the matching requirements/*.in and run "
                f"scripts/lock.sh."
            )
            continue
        for layer in found_in:
            locked = locks[layer][name]
            if version not in locked:
                failures.append(
                    f"pin drift: pyproject.toml has {name}=={version} but "
                    f"requirements/{layer}.txt has {name}=={'/'.join(sorted(locked))}. "
                    f"Run scripts/lock.sh."
                )

    if failures:
        print("FAIL: dependency pinning is not airtight:")
        for f in failures:
            print(f"  {f}")
        return 1

    counts = ", ".join(f"{layer}={len(locks.get(layer, {}))}" for layer in LAYERS)
    print(f"  clean ({len(declared)} declared, all exact; locked packages: {counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
