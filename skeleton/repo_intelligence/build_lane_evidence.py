"""#807 build lane (B001-B010) structural-evidence audit.

Maps each build-lane batch to the module(s), public symbols, focused tests and
source/AI mirror pairs that implement it on current ``main`` and checks, without
executing any build, that the evidence is still present:

* each module imports and exposes the required symbols;
* each focused test file and each non-Python artefact exists;
* mirrored source files are byte-identical (SHA-256) to their mirror.

This is *structural* evidence only (see #807 "Evidence standard"): it proves the
contract surface did not silently regress, not that a batch is SOTA-ready.
The report is canonical JSON with a SHA-256 digest so it can be attached to a
``repo-intel`` handoff note.  Anything missing fails closed.

Run ``python -m skeleton.repo_intelligence.build_lane_evidence`` for a report.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .batch_plan import load_plan

SCHEMA = "repo_intelligence.build_lane_evidence.v1"
BUILD_LANE = tuple(f"B{i:03d}" for i in range(1, 11))
PRIORITY = ("B004", "B005", "B007", "B009")
MAX_FILE_BYTES = 8 * 1024 * 1024


def _find_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "skeleton").is_dir():
            return parent
    raise BuildLaneEvidenceError("repository root not found")


class BuildLaneEvidenceError(ValueError):
    """Evidence specification or audit input is invalid."""


REPO_ROOT = _find_root(Path(__file__))


@dataclass(frozen=True)
class BatchEvidence:
    batch_id: str
    modules: Mapping[str, tuple[str, ...]]  # module -> required symbols
    tests: tuple[str, ...] = ()
    artefacts: tuple[str, ...] = ()
    mirrors: tuple[tuple[str, str], ...] = ()  # (source, mirror) relative paths
    notes: str = ""

    def __post_init__(self) -> None:
        if self.batch_id not in BUILD_LANE:
            raise BuildLaneEvidenceError(f"not a build-lane batch: {self.batch_id!r}")
        for rel in (*self.tests, *self.artefacts, *(p for pair in self.mirrors for p in pair)):
            _check_rel(rel)


def _check_rel(rel: str) -> None:
    p = Path(rel)
    if not rel or p.is_absolute() or ".." in p.parts or "\x00" in rel:
        raise BuildLaneEvidenceError(f"evidence path must be repo-relative: {rel!r}")


_T = "skeleton/testing/"
_CORE = "skeleton/ai/build/core/"
_RI = "skeleton/ai/build/repo_intelligence/"


def _mirror(name: str, base: str = "skeleton/build/", mirror: str = _CORE) -> tuple[str, str]:
    return (base + name, mirror + name)


DEFAULT_EVIDENCE: tuple[BatchEvidence, ...] = (
    BatchEvidence("B001", {"skeleton.repo_intelligence.git_index": ("GitIndex", "GitIndexSnapshot", "GitIndexError"),
                           "skeleton.repo_intelligence.batch_plan": ("load_plan", "snapshot_b001", "BatchPlan")},
                  tests=(_T + "test_repo_intelligence_git_index.py", _T + "test_repo_intelligence_batch_plan.py"),
                  artefacts=("skeleton/repo_intelligence/game_creation_batches.json",),
                  mirrors=(_mirror("git_index.py", "skeleton/repo_intelligence/", _RI),
                           _mirror("batch_plan.py", "skeleton/repo_intelligence/", _RI),
                           _mirror("game_creation_batches.json", "skeleton/repo_intelligence/", _RI))),
    BatchEvidence("B002", {"skeleton.build.incremental_graph": ("IncrementalBuildGraph", "build_incremental_graph", "CriticalPath")},
                  tests=(_T + "test_incremental_graph.py",), mirrors=(_mirror("incremental_graph.py"),)),
    BatchEvidence("B003", {"skeleton.build.cache_contract": ("CacheKey", "EvictionPolicy", "build_cache_key")},
                  tests=(_T + "test_cache_contract.py",), mirrors=(_mirror("cache_contract.py"),)),
    BatchEvidence("B004", {}, tests=(_T + "test_toolchain_bootstrap.py",),
                  artefacts=(".mise.toml", "scripts/verify_toolchain_bootstrap.py", "scripts/check_toolchain_contract.py",
                             "docs/TOOLCHAIN_BOOTSTRAP.md"),
                  notes="bootstrap surface lives in scripts/ + .mise.toml; audited read-only"),
    BatchEvidence("B005", {"skeleton.build.parallel_scheduler": ("ParallelBuildPlan", "ResourceCapacity", "ResourceRequest", "ScheduleWave")},
                  tests=(_T + "test_parallel_scheduler.py",), mirrors=(_mirror("parallel_scheduler.py"),)),
    BatchEvidence("B006", {}, artefacts=("scripts/artifact_reference.py", "scripts/check_artifact_policy.py", "docs/ARTIFACT_POLICY.md"),
                  notes="large-artifact policy is scripts/docs only; binary migration blocked per #807"),
    BatchEvidence("B007", {"skeleton.build.asset_pipeline": ("AssetPipeline", "AssetSpec", "AssetRebuildPlan", "build_asset_pipeline")},
                  tests=(_T + "test_asset_pipeline.py",), mirrors=(_mirror("asset_pipeline.py"),)),
    BatchEvidence("B008", {"skeleton.build.remote_build": ("RemoteBuildPlan", "RemoteBuildJob", "ArtifactTransferManifest")},
                  tests=(_T + "test_remote_build.py", _T + "test_build_farm.py"), mirrors=(_mirror("remote_build.py"),)),
    BatchEvidence("B009", {"skeleton.build.build_observability": ("BuildTelemetry", "BuildRegressionBudget", "BuildBudgetDecision", "NodeObservation")},
                  tests=(_T + "test_build_observability.py",), mirrors=(_mirror("build_observability.py"),)),
    BatchEvidence("B010", {"skeleton.build.release_graph": ("ReleaseGraph", "ReleaseRun", "ReproducibilityDecision")},
                  tests=(_T + "test_release_graph.py",), mirrors=(_mirror("release_graph.py"),)),
)


@dataclass
class BatchResult:
    batch_id: str
    title: str
    problems: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems and self.checked > 0

    def to_record(self) -> dict[str, Any]:
        return {"batch_id": self.batch_id, "title": self.title, "ok": self.ok, "checked": self.checked,
                "problems": sorted(self.problems)}


@dataclass
class LaneReport:
    results: list[BatchResult]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def to_record(self) -> dict[str, Any]:
        body = {"schema": SCHEMA, "ok": self.ok, "batches": [r.to_record() for r in self.results]}
        body["digest"] = hashlib.sha256(_canonical(body)).hexdigest()
        return body


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha256(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise BuildLaneEvidenceError(f"file too large to hash: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_evidence_module(module_name: str):
    """Audit only code owners enumerated by the default build-lane registry."""
    if module_name == "skeleton.repo_intelligence.git_index":
        return importlib.import_module("skeleton.repo_intelligence.git_index")
    if module_name == "skeleton.repo_intelligence.batch_plan":
        return importlib.import_module("skeleton.repo_intelligence.batch_plan")
    if module_name == "skeleton.build.incremental_graph":
        return importlib.import_module("skeleton.build.incremental_graph")
    if module_name == "skeleton.build.cache_contract":
        return importlib.import_module("skeleton.build.cache_contract")
    if module_name == "skeleton.build.parallel_scheduler":
        return importlib.import_module("skeleton.build.parallel_scheduler")
    if module_name == "skeleton.build.asset_pipeline":
        return importlib.import_module("skeleton.build.asset_pipeline")
    if module_name == "skeleton.build.remote_build":
        return importlib.import_module("skeleton.build.remote_build")
    if module_name == "skeleton.build.build_observability":
        return importlib.import_module("skeleton.build.build_observability")
    if module_name == "skeleton.build.release_graph":
        return importlib.import_module("skeleton.build.release_graph")
    raise BuildLaneEvidenceError("unregistered build-lane module owner")


def audit_batch(spec: BatchEvidence, *, root: Path = REPO_ROOT, title: str = "") -> BatchResult:
    res = BatchResult(spec.batch_id, title)
    for module, symbols in sorted(spec.modules.items()):
        res.checked += 1
        try:
            mod = _load_evidence_module(module)
        except Exception as exc:  # fail closed: any import failure is a regression
            res.problems.append(f"import {module}: {type(exc).__name__}")
            continue
        for sym in symbols:
            res.checked += 1
            if not hasattr(mod, sym):
                res.problems.append(f"missing symbol {module}.{sym}")
    for rel in (*spec.tests, *spec.artefacts):
        res.checked += 1
        if not (root / rel).is_file():
            res.problems.append(f"missing file {rel}")
    for src, dst in spec.mirrors:
        res.checked += 1
        a, b = root / src, root / dst
        if not a.is_file() or not b.is_file():
            res.problems.append(f"mirror pair incomplete {src} -> {dst}")
        elif _sha256(a) != _sha256(b):
            res.problems.append(f"mirror drift {src} != {dst}")
    return res


def audit(evidence: Iterable[BatchEvidence] = DEFAULT_EVIDENCE, *, root: Path = REPO_ROOT,
          batches: Sequence[str] | None = None) -> LaneReport:
    specs = {e.batch_id: e for e in evidence}
    wanted = tuple(batches) if batches is not None else BUILD_LANE
    unknown = [b for b in wanted if b not in BUILD_LANE]
    if unknown:
        raise BuildLaneEvidenceError(f"not build-lane batches: {unknown}")
    try:
        titles = {b.id: b.title for b in load_plan().batches}
    except Exception:  # plan unavailable: titles are cosmetic, audit still runs
        titles = {}
    results = []
    for bid in wanted:
        spec = specs.get(bid)
        if spec is None:
            results.append(BatchResult(bid, titles.get(bid, ""), ["no evidence specification"]))
        else:
            results.append(audit_batch(spec, root=root, title=titles.get(bid, "")))
    return LaneReport(results)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    report = audit(batches=args or None)
    print(json.dumps(report.to_record(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


__all__ = ["BUILD_LANE", "DEFAULT_EVIDENCE", "PRIORITY", "SCHEMA", "BatchEvidence", "BatchResult",
           "BuildLaneEvidenceError", "LaneReport", "audit", "audit_batch", "main"]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
