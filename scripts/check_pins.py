#!/usr/bin/env python3
"""Assert the dependency set is exactly pinned and internally consistent.

Five properties, all of which have to hold for NF11 (a third party reconstructs the run
from the manifest and the repository at a signed commit):

  1. Nothing is loose. Every requirement in pyproject.toml and every line in the
     lockfiles is `==`, not `>=` or `~=`.
  2. pyproject.toml and the lockfiles agree. Two sources of truth that disagree are worse
     than one that is vague, because the disagreement is silent.
  3. Every lockfile entry carries hashes. A pinned version fixes what you asked for; a
     hash fixes what you received.
  4. The base dependency set is the `generate` layer and no more (F31, §5.3). This is
     the one a *target* installs, so a base install must not reach the ML stack. Checked
     against the generate lockfile rather than against a list of banned names, because a
     list only catches the packages someone thought to ban.
  5. The layers agree with each other. `score` is `generate` plus the ML stack, `dev` is
     `score` plus tooling. A package in two lockfiles at two versions means the boundary
     tests exercise different software from the one that ships, and nothing else in the
     build would say so. Added in Phase B2 alongside the `audit` layer, which made a
     fourth chance to disagree.

Run via scripts/lock.sh, or directly.
"""

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_DIR = REPO_ROOT / "requirements"
#: Ordered by containment: generate ⊂ score ⊂ dev. `audit` is disjoint — CI-only
#: scanners, kept out of the set a contributor installs (see requirements/audit.in).
LAYERS = ("generate", "score", "dev", "audit")

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
    base_requirements = list(project.get("dependencies", []))
    all_requirements = list(base_requirements)
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

    # 4: the base install is the generate layer, not a superset of it.
    #
    # A target installing the package gets `dependencies` and nothing else. If a name
    # lands there that the generate lockfile does not resolve, the base install has
    # quietly grown past the boundary §5.3 draws — which is how the ML stack ends up on
    # a machine that was only ever meant to fire HTTP requests.
    generate_lock = locks.get("generate", {})
    if generate_lock:
        for requirement in base_requirements:
            match = PIN_RE.match(requirement.strip())
            if not match:
                continue
            name = normalise(match.group(1))
            if name not in generate_lock:
                failures.append(
                    f"pyproject.toml declares {name} as a base dependency, but it is "
                    f"not in requirements/generate.txt. The base set is the generate "
                    f"layer (F31, §5.3) — move it to an optional-dependencies extra, "
                    f"or add it to requirements/generate.in if it genuinely belongs "
                    f"in the set a target installs."
                )

    # 5: the layers agree with one another.
    #
    # Every lockfile is resolved from its own .in file, and uv resolves each one
    # independently. Nothing before this made `httpx` in generate.txt and `httpx` in
    # score.txt the same version — the boundary tests would install one and the shipped
    # scorer the other, and both would pass. The failure is silent by construction,
    # which is the only kind worth a gate.
    everywhere: dict[str, dict[str, set[str]]] = {}
    for layer in LAYERS:
        for name, versions in locks.get(layer, {}).items():
            everywhere.setdefault(name, {})[layer] = versions

    for name, by_layer in sorted(everywhere.items()):
        if len(by_layer) < 2:
            continue
        # A package may legitimately carry several versions *within* one lockfile, when
        # environment markers select different ones per platform. The layers must offer
        # the same set, not collapse to a single version.
        distinct = {frozenset(versions) for versions in by_layer.values()}
        if len(distinct) > 1:
            detail = "; ".join(
                f"{layer}={'/'.join(sorted(versions))}"
                for layer, versions in sorted(by_layer.items())
            )
            failures.append(
                f"layer disagreement: {name} is pinned differently across lockfiles "
                f"({detail}). The layers are nested — score is generate plus the ML "
                f"stack — so a split version means the dependency-boundary tests and "
                f"the shipped scorer are running different software. Run "
                f"scripts/lock.sh to resolve them together."
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
