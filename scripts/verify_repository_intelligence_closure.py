#!/usr/bin/env python3
"""Independent verifier for VOL-021 repository intelligence closure.

The verifier does not import repository-intelligence implementation modules into
its own process. It inspects repository boundaries as files, executes the
implementation only in a fresh subprocess over a fixed synthetic cross-language
fixture, and independently judges the returned graph/impact/change-plan receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

from skeleton.contracts.canonical import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]

CANONICAL_GRAPH = "skeleton/repo_intelligence/repository_graph.py"
MIRROR_GRAPH = "skeleton/ai/build/repo_intelligence/repository_graph.py"
CANONICAL_EXTRACTOR = "skeleton/repo_intelligence/source_extraction.py"
MIRROR_EXTRACTOR = "skeleton/ai/build/repo_intelligence/source_extraction.py"
CANONICAL_PLANNER = "skeleton/repo_intelligence/change_planner.py"
MIRROR_PLANNER = "skeleton/ai/build/repo_intelligence/change_planner.py"
GRAPH_TEST = "skeleton/testing/test_vol021_repository_graph.py"
EXTRACTION_TEST = "skeleton/testing/test_vol021_source_extraction.py"
GIT_INDEX_TEST = "skeleton/testing/test_repo_intelligence_git_index.py"
WORKFLOW = ".github/workflows/repository-intelligence-closure.yml"
WORKFLOW_REQUIRED_PATHS = (
    CANONICAL_GRAPH,
    MIRROR_GRAPH,
    CANONICAL_EXTRACTOR,
    MIRROR_EXTRACTOR,
    CANONICAL_PLANNER,
    MIRROR_PLANNER,
    GRAPH_TEST,
    EXTRACTION_TEST,
    GIT_INDEX_TEST,
    "scripts/verify_repository_intelligence_closure.py",
    "tests/test_repository_intelligence_independent_verifier.py",
)

REQUIRED_GRAPH_TOKENS = (
    "class FileNode",
    "class DependencyEdge",
    "class RepositoryGraph",
    "canonical_json_bytes",
    "def impact(",
    "def tests_for(",
    "def owners_for(",
)
REQUIRED_EXTRACTOR_TOKENS = (
    "class SourceFile",
    "def build_repository_graph(",
    '"python"',
    '"typescript"',
    '"javascript"',
    '"java"',
    '"rust"',
    '"go"',
)
REQUIRED_PLANNER_TOKENS = (
    "class ChangePlan",
    "def plan_change(",
    'authority_scope:str="change-plan-only"',
)
FORBIDDEN_BOUNDARY_TOKENS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "requests.",
    "httpx.",
    "subprocess.",
    "os.system",
)

EXPECTED_EDGES = (
    ("app/main.go", "lib/util.go", "import"),
    ("com/x/A.java", "com/x/B.java", "import"),
    ("crate/main.rs", "crate/util.rs", "import"),
    ("pkg/use.ts", "pkg/core.py", "import"),
    ("tests/test_core.py", "pkg/core.py", "import"),
    ("tests/test_ui.py", "pkg/use.ts", "import"),
)
EXPECTED_IMPACT = (
    "pkg/core.py",
    "pkg/use.ts",
    "tests/test_core.py",
    "tests/test_ui.py",
)
EXPECTED_TESTS = ("tests/test_core.py", "tests/test_ui.py")
EXPECTED_OWNERS = ("core", "qa", "ui")
EXPECTED_CHANGED = ("pkg/core.py",)

_FIXTURE_PROGRAM = r"""
import hashlib
import json
from skeleton.repo_intelligence.change_planner import plan_change
from skeleton.repo_intelligence.source_extraction import SourceFile, build_repository_graph

def source(path, content, owner=None, tests=()):
    return SourceFile(
        path,
        content,
        hashlib.sha256(content.encode("utf-8")).hexdigest(),
        owner,
        tests,
    )

sources = (
    source("pkg/core.py", "VALUE = 1\n", "core", ("tests/test_core.py",)),
    source("pkg/use.ts", "import core from './core'\n", "ui", ("tests/test_ui.py",)),
    source("com/x/A.java", "import com.x.B;\n", "java"),
    source("com/x/B.java", "", "java"),
    source("crate/main.rs", "use crate::util;\n", "rust"),
    source("crate/util.rs", "", "rust"),
    source("app/main.go", 'import "lib/util"\n', "go"),
    source("lib/util.go", "", "go"),
    source("tests/test_core.py", "import pkg.core\n", "qa"),
    source("tests/test_ui.py", "import pkg.use\n", "qa"),
    source("misc/external.py", "import requests\n", "external"),
)

graph = build_repository_graph(sources)
plan = plan_change(graph, ("pkg/core.py",))
print(json.dumps(
    {
        "graph_digest": graph.digest,
        "edges": [list(edge) for edge in graph.edges],
        "changed_paths": list(plan.changed_paths),
        "impacted_paths": list(plan.impacted_paths),
        "required_tests": list(plan.required_tests),
        "owners": list(plan.owners),
        "authority_scope": plan.authority_scope,
    },
    sort_keys=True,
))
"""


class RepositoryIntelligenceVerificationError(RuntimeError):
    """Independent verification could not safely inspect repository state."""


def _read(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RepositoryIntelligenceVerificationError(
            f"cannot read {relative}"
        ) from exc


def _load_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepositoryIntelligenceVerificationError(
            f"cannot parse {relative}"
        ) from exc
    if not isinstance(payload, dict):
        raise RepositoryIntelligenceVerificationError(
            f"{relative} must contain an object"
        )
    return payload


def _find_volume(value: object, key: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("key") == key:
            return value
        for child in value.values():
            match = _find_volume(child, key)
            if match is not None:
                return match
    elif isinstance(value, list):
        for child in value:
            match = _find_volume(child, key)
            if match is not None:
                return match
    return None


def _expected_graph_digest() -> str:
    def digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    nodes = [
        {
            "path": "app/main.go",
            "language": "go",
            "digest": digest('import "lib/util"\n'),
            "owner": "go",
            "tests": (),
        },
        {
            "path": "com/x/A.java",
            "language": "java",
            "digest": digest("import com.x.B;\n"),
            "owner": "java",
            "tests": (),
        },
        {
            "path": "com/x/B.java",
            "language": "java",
            "digest": digest(""),
            "owner": "java",
            "tests": (),
        },
        {
            "path": "crate/main.rs",
            "language": "rust",
            "digest": digest("use crate::util;\n"),
            "owner": "rust",
            "tests": (),
        },
        {
            "path": "crate/util.rs",
            "language": "rust",
            "digest": digest(""),
            "owner": "rust",
            "tests": (),
        },
        {
            "path": "lib/util.go",
            "language": "go",
            "digest": digest(""),
            "owner": "go",
            "tests": (),
        },
        {
            "path": "misc/external.py",
            "language": "python",
            "digest": digest("import requests\n"),
            "owner": "external",
            "tests": (),
        },
        {
            "path": "pkg/core.py",
            "language": "python",
            "digest": digest("VALUE = 1\n"),
            "owner": "core",
            "tests": ("tests/test_core.py",),
        },
        {
            "path": "pkg/use.ts",
            "language": "typescript",
            "digest": digest("import core from './core'\n"),
            "owner": "ui",
            "tests": ("tests/test_ui.py",),
        },
        {
            "path": "tests/test_core.py",
            "language": "python",
            "digest": digest("import pkg.core\n"),
            "owner": "qa",
            "tests": (),
        },
        {
            "path": "tests/test_ui.py",
            "language": "python",
            "digest": digest("import pkg.use\n"),
            "owner": "qa",
            "tests": (),
        },
    ]
    return hashlib.sha256(
        canonical_json_bytes({"nodes": nodes, "edges": EXPECTED_EDGES})
    ).hexdigest()


def _run_fixture(root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + existing if existing else "")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _FIXTURE_PROGRAM],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RepositoryIntelligenceVerificationError(
            "cannot execute repository-intelligence fixture"
        ) from exc
    if proc.returncode != 0:
        raise RepositoryIntelligenceVerificationError(
            "repository-intelligence fixture failed: "
            + proc.stderr.strip()[:1200]
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RepositoryIntelligenceVerificationError(
            "repository-intelligence fixture emitted invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise RepositoryIntelligenceVerificationError(
            "repository-intelligence fixture receipt must be an object"
        )
    return payload


def _canonical_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise RepositoryIntelligenceVerificationError(
            f"fixture {field} must be a string array"
        )
    return tuple(value)


def _validate_behavior(
    behavior: Mapping[str, Any],
    errors: list[str],
) -> None:
    raw_edges = behavior.get("edges")
    if (
        not isinstance(raw_edges, list)
        or any(
            not isinstance(edge, list)
            or len(edge) != 3
            or any(not isinstance(part, str) for part in edge)
            for edge in raw_edges
        )
    ):
        errors.append("fixture edges are malformed")
        edges: tuple[tuple[str, str, str], ...] = ()
    else:
        edges = tuple(tuple(edge) for edge in raw_edges)

    if edges != EXPECTED_EDGES:
        errors.append(
            "cross-language dependency graph mismatch: "
            f"expected {EXPECTED_EDGES!r}, got {edges!r}"
        )

    if any(edge[0] == "misc/external.py" for edge in edges):
        errors.append("external dependency was guessed as an internal edge")

    for field, expected in (
        ("changed_paths", EXPECTED_CHANGED),
        ("impacted_paths", EXPECTED_IMPACT),
        ("required_tests", EXPECTED_TESTS),
        ("owners", EXPECTED_OWNERS),
    ):
        try:
            actual = _canonical_tuple(behavior.get(field), field)
        except RepositoryIntelligenceVerificationError as exc:
            errors.append(str(exc))
            continue
        if actual != expected:
            errors.append(
                f"{field} mismatch: expected {expected!r}, got {actual!r}"
            )

    if behavior.get("authority_scope") != "change-plan-only":
        errors.append("change planner widened mutation authority")

    graph_digest = behavior.get("graph_digest")
    if graph_digest != _expected_graph_digest():
        errors.append("repository graph digest is not shared-canonical identity")


def verify_repository(
    root: Path = ROOT,
    *,
    behavior: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []

    mirror_pairs = (
        (CANONICAL_GRAPH, MIRROR_GRAPH),
        (CANONICAL_EXTRACTOR, MIRROR_EXTRACTOR),
        (CANONICAL_PLANNER, MIRROR_PLANNER),
    )
    required_paths = (
        CANONICAL_GRAPH,
        MIRROR_GRAPH,
        CANONICAL_EXTRACTOR,
        MIRROR_EXTRACTOR,
        CANONICAL_PLANNER,
        MIRROR_PLANNER,
        GRAPH_TEST,
        EXTRACTION_TEST,
        GIT_INDEX_TEST,
        WORKFLOW,
        "machine/ai_master_plan.json",
    )
    for relative in required_paths:
        if not (root / relative).is_file():
            errors.append(f"repository-intelligence required file missing: {relative}")

    texts: dict[str, str] = {}
    for relative in (
        CANONICAL_GRAPH,
        CANONICAL_EXTRACTOR,
        CANONICAL_PLANNER,
    ):
        if (root / relative).is_file():
            texts[relative] = _read(root, relative)

    for token in REQUIRED_GRAPH_TOKENS:
        if token not in texts.get(CANONICAL_GRAPH, ""):
            errors.append(f"{CANONICAL_GRAPH} lost required token: {token}")
    for token in REQUIRED_EXTRACTOR_TOKENS:
        if token not in texts.get(CANONICAL_EXTRACTOR, ""):
            errors.append(f"{CANONICAL_EXTRACTOR} lost required token: {token}")
    for token in REQUIRED_PLANNER_TOKENS:
        if token not in texts.get(CANONICAL_PLANNER, ""):
            errors.append(f"{CANONICAL_PLANNER} lost required token: {token}")

    if (root / WORKFLOW).is_file():
        workflow = _read(root, WORKFLOW)
        for required in WORKFLOW_REQUIRED_PATHS:
            if required not in workflow:
                errors.append(
                    f"{WORKFLOW} lost repository-intelligence coverage: {required}"
                )

    if "json.dumps" in texts.get(CANONICAL_GRAPH, ""):
        errors.append(
            f"{CANONICAL_GRAPH} regressed to a private JSON identity serializer"
        )

    for relative, text in texts.items():
        for token in FORBIDDEN_BOUNDARY_TOKENS:
            if token in text:
                errors.append(
                    f"{relative} owns forbidden execution/provider token: {token}"
                )

    mirror_digests: dict[str, dict[str, str]] = {}
    for canonical, mirror in mirror_pairs:
        if not (root / canonical).is_file() or not (root / mirror).is_file():
            continue
        canonical_bytes = (root / canonical).read_bytes()
        mirror_bytes = (root / mirror).read_bytes()
        canonical_digest = hashlib.sha256(canonical_bytes).hexdigest()
        mirror_digest = hashlib.sha256(mirror_bytes).hexdigest()
        mirror_digests[canonical] = {
            "canonical": canonical_digest,
            "mirror": mirror_digest,
        }
        if canonical_bytes != mirror_bytes:
            errors.append(f"canonical AI mirror drift: {canonical} != {mirror}")

    try:
        plan = _load_json(root, "machine/ai_master_plan.json")
        volume = _find_volume(plan, "VOL-021")
    except RepositoryIntelligenceVerificationError as exc:
        errors.append(str(exc))
        volume = None

    if volume is None:
        errors.append("VOL-021 is missing from canonical masterplan")
    else:
        joined = " ".join(
            str(item) for item in volume.get("requirements", ())
        ).lower()
        for phrase in (
            "repository intelligence",
            "index freshness",
            "impact queries",
        ):
            if phrase not in joined:
                errors.append(
                    f"VOL-021 requirement drift: missing phrase {phrase!r}"
                )
        capabilities = set(
            str(item) for item in volume.get("capabilities", ())
        )
        for capability in (
            "repository graph",
            "symbol search",
            "impact analysis",
        ):
            if capability not in capabilities:
                errors.append(
                    f"VOL-021 capability drift: {capability}"
                )
        gaps = tuple(str(item) for item in volume.get("gaps", ()))
        expected_gap = (
            "independent cross-language repository-graph, ownership/test impact, "
            "and change-planner verification remains pending"
        )
        if gaps not in ((), (expected_gap,)):
            errors.append(
                "VOL-021 contains unexpected implementation gaps: "
                + ", ".join(gaps)
            )

    if behavior is None:
        try:
            observed_behavior = _run_fixture(root)
        except RepositoryIntelligenceVerificationError as exc:
            errors.append(str(exc))
            observed_behavior = {}
    else:
        observed_behavior = dict(behavior)
    _validate_behavior(observed_behavior, errors)

    boundary_digests: dict[str, str] = {}
    for relative in required_paths + (__file_relative(),):
        path = root / relative
        if path.is_file():
            boundary_digests[relative] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-repository-intelligence-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "mirror_digests": mirror_digests,
        "fixture": observed_behavior,
        "boundary_digests": boundary_digests,
        "errors": errors,
        "valid": not errors,
    }


def __file_relative() -> str:
    try:
        return Path(__file__).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "scripts/verify_repository_intelligence_closure.py"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except RepositoryIntelligenceVerificationError as exc:
        print(f"independent-repository-intelligence: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("independent-repository-intelligence: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-repository-intelligence: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"edges={len(receipt['fixture'].get('edges', ()))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
