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
