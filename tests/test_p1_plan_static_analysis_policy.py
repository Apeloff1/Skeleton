from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_p1_plan_static_analysis.py"
FILES = (
    Path("machine/p1_plan_static_analysis_policy.json"),
    Path("machine/ai_p1_task_backlog.json"),
    Path("skeleton/intelligence/plan_static_analyzer.py"),
    Path("skeleton/ai/runtime/intelligence/plan_static_analyzer.py"),
    Path("skeleton/intelligence/strategy_registry.py"),
    Path("skeleton/ai/runtime/intelligence/strategy_registry.py"),
)


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_p1_plan_static_analysis",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo(tmp_path: Path) -> Path:
    for rel in FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    return tmp_path


def test_repository_plan_analysis_authority_is_valid() -> None:
    module = _module()
    summary = module.validate_repository(ROOT)

    assert summary["valid"] is True
    assert summary["task_id"] == "P1-INTEL-05"
    assert summary["accountability_ref"] == "ACC-P1-INTEL-05"
    assert summary["dependency_count"] == 2
    assert summary["parallel_planning_root_present"] is False
    assert len(summary["analyzer_digest"]) == 64


def test_source_mirror_drift_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    mirror = root / "skeleton/ai/runtime/intelligence/plan_static_analyzer.py"
    mirror.write_text(
        mirror.read_text(encoding="utf-8") + "\n# semantic drift\n",
        encoding="utf-8",
    )

    module = _module()
    try:
        module.validate_repository(root)
    except module.PlanAnalysisPolicyError as exc:
        assert "source/mirror parity drift" in str(exc)
    else:
        raise AssertionError("plan analyzer mirror drift unexpectedly validated")


def test_dependency_drift_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    backlog = root / "machine/ai_p1_task_backlog.json"
    payload = json.loads(backlog.read_text(encoding="utf-8"))
    task = next(row for row in payload["tasks"] if row["task_id"] == "P1-INTEL-05")
    task["depends_on"] = ["P1-INTEL-03"]
    backlog.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    module = _module()
    try:
        module.validate_repository(root)
    except module.PlanAnalysisPolicyError as exc:
        assert "dependency drift" in str(exc)
    else:
        raise AssertionError("weakened dependency set unexpectedly validated")


def test_parallel_planning_root_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    planning = root / "skeleton/planning"
    planning.mkdir(parents=True)
    (planning / "__init__.py").write_text("", encoding="utf-8")

    module = _module()
    try:
        module.validate_repository(root)
    except module.PlanAnalysisPolicyError as exc:
        assert "parallel skeleton/planning authority" in str(exc)
    else:
        raise AssertionError("parallel planning authority unexpectedly validated")


def test_policy_semantics_cannot_be_weakened(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    policy = root / "machine/p1_plan_static_analysis_policy.json"
    payload = json.loads(policy.read_text(encoding="utf-8"))
    payload["semantics"]["side_effect_compensation_required"] = False
    policy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    module = _module()
    try:
        module.validate_repository(root)
    except module.PlanAnalysisPolicyError as exc:
        assert "semantics drift" in str(exc)
    else:
        raise AssertionError("weakened plan semantics unexpectedly validated")
