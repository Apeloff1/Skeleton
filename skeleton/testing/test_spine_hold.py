from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.spine_hold import SpineHold


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_hold_applies_nothing(tmp_path: Path) -> None:
    hold = SpineHold(tmp_path / "hold.sqlite")
    card = hold.hold(
        tenant_id="tenant-hold",
        outbox_id="21212121-2121-4121-8121-212121212121",
        reason="apply-not-landed",
        now=BASE,
    )
    assert card["applied"] == 0
    assert card["completion_checkbox"] is False
    hold.close()
