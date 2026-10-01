from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_spine_bind_recovery import (
    EXPECTED_SEAMS,
    MIRRORED,
    SpineBindRecoveryControlError,
    build_report,
    verify_manifest,
    verify_mirror_parity,
)


def _write_fixture(root: Path) -> None:
    canonical = root / "skeleton" / "persistence"
    mirror = root / "skeleton" / "ai" / "runtime" / "persistence"
    canonical.mkdir(parents=True)
    mirror.mkdir(parents=True)
    for name in MIRRORED:
        content = f"# {name}\n"
        if name == "spine_manifest.py":
            base = [(f"seam-{index}", f"law-{index}") for index in range(88)]
            base.extend(EXPECTED_SEAMS.items())
            content = "SEAMS = " + repr(tuple(base)) + "\n"
        (canonical / name).write_text(content, encoding="utf-8")
        (mirror / name).write_text(content, encoding="utf-8")

    plan = root / "docs" / "plan"
    plan.mkdir(parents=True)
    (plan / "P2_SPINE_MASTERPLAN.md").write_text(
        "\n".join(
            [
                "- Bind card sealed: 100%",
                "Expect `count` 105",
                "Bind snapshot",
                "Bind recovery",
                "Bind checkpoint",
                "Bind checkpoint replay",
                "Bind checkpoint tenant",
                "Bind checkpoint chain",
                "Bind bundle",
                "Bind bundle verify",
                "`ready`, `activated`, `apply_landed`, `live_motor`, "
                "`dispatcher_running`, `ci_green`, and `merged` remain false",
            ]
        ),
        encoding="utf-8",
    )


def test_control_accepts_complete_dark_fixture(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    report = build_report(tmp_path)

    assert report["valid"] is True
    assert report["mirror_count"] == len(MIRRORED)
    assert report["manifest"]["count"] == 105
    assert report["masterplan"]["bind_card_percent"] == 100
    assert report["masterplan"]["activation_claimed"] is False
    assert report["completion_checkbox"] is False


def test_mirror_drift_fails_closed(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    mirror = (
        tmp_path
        / "skeleton"
        / "ai"
        / "runtime"
        / "persistence"
        / "spine_bind_bundle.py"
    )
    mirror.write_text("# drift\n", encoding="utf-8")

    with pytest.raises(SpineBindRecoveryControlError, match="mirror drift"):
        verify_mirror_parity(tmp_path)


def test_manifest_missing_recovery_seam_fails_closed(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    path = tmp_path / "skeleton" / "persistence" / "spine_manifest.py"
    seams = list(build_report(tmp_path)["manifest"]["recovery_seams"])
    assert seams

    full_manifest = [(f"seam-{index}", f"law-{index}") for index in range(88)]
    full_manifest.extend(EXPECTED_SEAMS.items())
    missing_name = seams[-1]
    mutated = [
        ("replacement", "not-the-required-seam") if name == missing_name else (name, law)
        for name, law in full_manifest
    ]
    assert len(mutated) == 105
    path.write_text("SEAMS = " + repr(tuple(mutated)) + "\n", encoding="utf-8")

    with pytest.raises(
        SpineBindRecoveryControlError,
        match="missing or changed recovery seam",
    ):
        verify_manifest(tmp_path)
