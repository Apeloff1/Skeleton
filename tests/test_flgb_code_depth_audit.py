"""Pure regression coverage for the pinned FLGB static-depth reporter."""
from pathlib import Path

import pytest

from scripts.audit_flgb_code_depth import (
    audit, inspect_contract, inspect_python, _relative_module_path,
)

SHA = "a" * 40


def test_forwarding_source_requires_delegated_runtime_evidence():
    files = {"skeleton/inference/wrapper.py", "skeleton/inference/flgb_runtime.py"}
    result = inspect_python(
        "skeleton/inference/wrapper.py",
        'from .flgb_runtime import OperationEnvelope\n__all__ = ["OperationEnvelope"]\n',
        files,
    )
    assert result["syntax_ok"] is True
    assert result["kind"] == "forwarding-module"
    assert result["unresolved_relative_modules"] == []
    assert "no-local-executable-definition" in result["warnings"]
    assert _relative_module_path("skeleton/inference/wrapper.py", 1, "flgb_runtime") == "skeleton/inference/flgb_runtime"


def test_missing_relative_owner_reported_without_import_execution():
    result = inspect_python("skeleton/game/entry.py", "from .missing import create_game\n",
                            {"skeleton/game/entry.py"})
    assert result["unresolved_relative_modules"] == ["skeleton/game/missing"]
    assert "missing-relative-import-module" in result["warnings"]


def test_assertions_are_detected_but_not_executed():
    result = inspect_python("tests/test_example.py",
                            "def test_example():\n    assert 2 + 2 == 4\n",
                            {"tests/test_example.py"}, test=True)
    assert result["syntax_ok"]
    assert result["test_cases"] == 1
    assert result["assertion_sites"] == 1
    assert not result["warnings"]


def test_syntax_error_and_empty_test_are_reported():
    broken = inspect_python("app/a.py", "def broken(:\n", {"app/a.py"})
    assert not broken["syntax_ok"]
    assert broken["warnings"][0].startswith("python-syntax:")
    empty = inspect_python("tests/test_empty.py", "import unittest\n",
                           {"tests/test_empty.py"}, test=True)
    assert "no-test-function-declared" in empty["warnings"]
    assert "no-direct-assertion-site" in empty["warnings"]


@pytest.mark.parametrize("data,expected", [
    ('{"type":"object","properties":{}}', True),
    ('{"title":"not a typed schema"}', False),
    ('{"type":"object","type":"array"}', False),
    ('{"type": NaN}', False),
])
def test_contract_structure_and_duplicates(data, expected):
    result = inspect_contract("contracts/demo.json", data)
    assert result["schema_shape"] is expected


def test_pinned_reader_and_no_completion_claim():
    targets = ("skeleton/inference/wrapper.py", "skeleton/inference/contracts/wrapper.json",
               "tests/flgb/test_wrapper.py")
    task = {
        "id": "FLGB-01-T01", "plane_id": "FLGB-01", "subsystem": "operation envelope",
        "implementation_target": targets[0], "contract_target": targets[1],
        "test_target": targets[2], "state": "implemented-pending-verification",
        "implementation_signed": False, "independent_verification_signed": False,
    }
    manifest = {
        "task_count": 1, "plane_count": 1, "tasks": [task],
        "planes": [{"id": "FLGB-01", "task_ids": [task["id"]]}],
    }
    data = {
        targets[0]: "from .runtime import Envelope\n",
        targets[1]: '{"type":"object","properties":{"id":{"type":"string"}}}',
        targets[2]: "def test_envelope():\n    assert True\n",
    }
    seen = []
    def reader(root, sha, path):
        seen.append((sha, path))
        return data[path]
    report = audit(manifest, set(targets), SHA, Path("."), start=0, count=1,
                   reader=reader)
    assert seen == [(SHA, p) for p in targets]
    assert report["completion_claim"] is False
    assert report["files_present_in_all_reviewed_tasks"] == 1
    assert report["static_counts"]["implementation_forwarding-module"] == 1
    assert "missing-relative-import-module" in report["items"][0]["implementation"]["warnings"]


def test_relative_module_owner_is_tracked_without_importing_it():
    tracked = {"skeleton/inference/wrapper.py", "skeleton/inference/flgb_runtime.py"}
    result = inspect_python(
        "skeleton/inference/wrapper.py",
        "from .flgb_runtime import OperationEnvelope, FLGBInferenceError\n",
        tracked,
    )
    assert result["unresolved_relative_modules"] == []
    assert result["relative_owner_imports"] == [{
        "path": "skeleton/inference/flgb_runtime.py",
        "symbols": ["OperationEnvelope", "FLGBInferenceError"],
    }]


def test_from_dot_import_sibling_module_is_not_silently_skipped():
    result = inspect_python(
        "skeleton/inference/wrapper.py", "from . import flgb_runtime\n",
        {"skeleton/inference/wrapper.py", "skeleton/inference/flgb_runtime.py"},
    )
    assert result["relative_owner_imports"] == [{
        "path": "skeleton/inference/flgb_runtime.py", "symbols": [],
    }]
    assert result["unresolved_relative_modules"] == []


def test_package_export_is_ambiguous_not_falsely_called_missing():
    result = inspect_python(
        "skeleton/inference/wrapper.py", "from . import OperationEnvelope\n",
        {"skeleton/inference/wrapper.py", "skeleton/inference/__init__.py"},
    )
    assert result["unresolved_relative_modules"] == []
    assert result["ambiguous_package_exports"] == [{
        "package": "skeleton/inference", "symbol": "OperationEnvelope",
    }]


def test_from_dot_import_truly_missing_name_without_package_owner_is_reported():
    result = inspect_python(
        "skeleton/inference/wrapper.py", "from . import lost\n",
        {"skeleton/inference/wrapper.py"},
    )
    assert result["unresolved_relative_modules"] == ["skeleton/inference/lost"]
    assert "missing-relative-import-module" in result["warnings"]


def test_relative_import_cannot_escape_root_package():
    result = inspect_python(
        "skeleton/inference/wrapper.py", "from ...outside import Invalid\n",
        {"skeleton/inference/wrapper.py"},
    )
    assert "relative-import-escapes-package" in result["warnings"]
