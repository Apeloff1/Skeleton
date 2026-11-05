from datetime import datetime, timezone

import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.maintenance_window import Freeze, Window, may_deploy

TUE_10 = int(datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc).timestamp())
TUE_18 = int(datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc).timestamp())
WINDOWS = [Window.parse("tue 08:00-15:00")]


def test_window_logic():
    assert may_deploy(TUE_10, tier="production", windows=WINDOWS) == (True, "in-window")
    assert may_deploy(TUE_18, tier="production", windows=WINDOWS) == (False, "outside-window")
    assert may_deploy(TUE_18, tier="dev", windows=[])[0]
    assert may_deploy(TUE_10, tier="staging", windows=[]) == (False, "no-windows-configured")


def test_freeze_overrides_window():
    freeze = Freeze(TUE_10 - 1, TUE_10 + 1, "launch")
    assert may_deploy(TUE_10, tier="production", windows=WINDOWS, freezes=[freeze]) == (False, "freeze:launch")


def test_parse_errors():
    for bad in ["tue", "xyz 08:00-09:00", "tue 10:00-09:00"]:
        with pytest.raises(DeliveryError):
            Window.parse(bad)
    with pytest.raises(DeliveryError):
        Freeze(5, 5, "x")

def test_window_parser_rejects_invalid_clock_normalization():
    for bad in ("tue 08:60-10:00", "tue 24:00-24:00",
                "tue 08:00-24:01", "tue 99:00-10:00",
                "tue 08:00-10:60", "tue 8:00-10:00",
                "tue 08:00-10:00 trailing"):
        with pytest.raises(DeliveryError):
            Window.parse(bad)
    assert Window.parse("tue 23:30-24:00") == Window("tue", 1410, 1440)


def test_freeze_rejects_invalid_timestamp_and_reason_evidence():
    for start, end, reason in ((True, 100, "x"), (1.0, 100, "x"),
                               (-1, 100, "x"), (1, 2.0, "x"),
                               (1, 2, ""), (1, 2, "forged" + chr(10) + "reason")):
        with pytest.raises(DeliveryError):
            Freeze(start, end, reason)


def test_deploy_rejects_unknown_tiers_and_invalid_timestamps():
    from skeleton.ai.build.core.delivery import maintenance_window as mirrored

    for module in (None, mirrored):
        deploy = may_deploy if module is None else module.may_deploy
        for tier in ("production-shadow", "", None):
            assert deploy(TUE_10, tier=tier, windows=WINDOWS) == (False, "unknown-tier")
        for ts in (True, -1, 1.0, 253402300800):
            assert deploy(ts, tier="production", windows=WINDOWS) == (
                False, "invalid-timestamp"
            )
        with pytest.raises(DeliveryError):
            (Window if module is None else module.Window)("tue", True, 600)


def test_deploy_fails_closed_on_unbounded_or_invalid_policy_inventories():
    from itertools import repeat
    from skeleton.ai.build.core.delivery import maintenance_window as mirrored

    for module in (None, mirrored):
        deploy = may_deploy if module is None else module.may_deploy
        freeze_type = Freeze if module is None else module.Freeze
        assert deploy(TUE_10, tier="production",
                      windows=repeat(WINDOWS[0], 257)) == (False, "too-many-windows")
        with pytest.raises(DeliveryError, match="freeze count exceeds"):
            deploy(TUE_10, tier="production", windows=WINDOWS,
                   freezes=repeat(freeze_type(0, 1, "old"), 4097))
        with pytest.raises(DeliveryError, match="invalid deployment freeze"):
            deploy(TUE_10, tier="production", windows=WINDOWS, freezes=[object()])
        with pytest.raises(DeliveryError, match="invalid deployment window"):
            deploy(TUE_10, tier="production", windows=[object()])
