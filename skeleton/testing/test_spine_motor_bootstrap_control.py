from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_spine_motor_bootstrap import (
    FILES,
    MotorBootstrapControlError,
    build_report,
    verify_no_driver_imports,
)


def test_live_repository_motor_bootstrap_control_is_dark() -> None:
    report = build_report(Path("."))

    assert report["valid"] is True
    assert report["index_count"] == 3
    assert report["mirror_count"] == len(FILES)
    assert len(report["plan_digest"]) == 64
    assert report["index_names"] == [
        "namespace_1_consumer_id_1_event_id_1",
        "namespace_1_consumer_id_1_operation_id_1",
        "namespace_1_tenant_id_1_resource_id_1",
    ]
    assert report["live_motor"] is False
    assert report["driver_imported"] is False
    assert report["activated"] is False
    assert report["completion_checkbox"] is False


def test_motor_bootstrap_control_rejects_driver_import(tmp_path: Path) -> None:
    persistence = tmp_path / "skeleton" / "persistence"
    persistence.mkdir(parents=True)
    for name in FILES:
        content = "import motor\n" if name == "spine_motor_bootstrap.py" else "# clean\n"
        (persistence / name).write_text(content, encoding="utf-8")

    with pytest.raises(MotorBootstrapControlError, match="live Mongo driver import"):
        verify_no_driver_imports(tmp_path)
