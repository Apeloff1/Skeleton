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
