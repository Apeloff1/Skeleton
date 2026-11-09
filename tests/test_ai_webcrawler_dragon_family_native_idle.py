"""Native Dragon idle observer: real local input gates, no forged idle time."""
from __future__ import annotations

import sys
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_family_native_idle import (
    NativeDragonIdleProbe,NativeHostSignals,NativeIdleUnavailable,
    os_input_idle_seconds,_linux_x11_idle_seconds,
)
from skeleton.ai.webcrawler.dragon_family_idle_host import DragonIdleHostControl
from skeleton.ai.webcrawler.dragon_family import IdleWindow


NOW=1800000000.0

def flags(**changes):
    data=dict(session_unlocked=True,user_foreground_active=False,
              running_foreground_jobs=0,resources_available=True,
              research_consent_active=True)
    data.update(changes)
    return NativeHostSignals(**data)


def native(idle=700.0,signals=None):
    return NativeDragonIdleProbe(
        clock=lambda:NOW+720,
        monotonic_clock=lambda:100.,
        input_idle_seconds=lambda:idle,
        host_signals=lambda:signals if signals is not None else flags(),
    )


def test_trusted_os_measurement_yields_idle_window_not_a_user_assertion():
    window=native().observe()
    assert isinstance(window,IdleWindow)
    assert window.now==NOW+720
    assert window.last_user_activity_at==NOW+20
    assert window.permitted(min_idle_seconds=300)
    assert window.consent is True


@pytest.mark.parametrize("signals",[
    flags(research_consent_active=False),
    flags(user_foreground_active=True),
    flags(resources_available=False),
    flags(running_foreground_jobs=2),
])
def test_host_budgets_and_consent_block_idle_despite_old_keyboard_input(signals):
    observed=native(signals=signals).observe()
    assert observed.permitted(min_idle_seconds=300) is False


def test_unconfirmed_unlocked_session_is_strictly_rejected():
    with pytest.raises(NativeIdleUnavailable,match="unlocked"):
        native(signals=flags(session_unlocked=False)).observe()


@pytest.mark.parametrize("measurement",[float("nan"),float("inf"),
    -1,86401,"900",None,True,1800000721.0])
def test_invalid_or_ancient_input_idle_does_not_enable_research(measurement):
    with pytest.raises(NativeIdleUnavailable):
        native(idle=measurement).observe()


def test_not_yet_idle_never_admits_new_work():
    assert not native(idle=299).observe().permitted(min_idle_seconds=300)


def test_clock_skew_or_very_slow_native_probe_fails_closed():
    clock=iter((100.,110.))
    delayed=NativeDragonIdleProbe(
        clock=lambda:NOW+720,
        monotonic_clock=lambda:next(clock),
        input_idle_seconds=lambda:900.,
        host_signals=flags,
    )
    with pytest.raises(NativeIdleUnavailable,match="stale"):
        delayed.observe()
    reversed_clock=iter((100.,99.))
    broken=NativeDragonIdleProbe(
        clock=lambda:NOW+720,
        monotonic_clock=lambda:next(reversed_clock),
        input_idle_seconds=lambda:900.,
        host_signals=flags,
    )
    with pytest.raises(NativeIdleUnavailable,match="stale"):
        broken.observe()


def test_missing_host_activity_or_input_sensor_denies_without_fallback():
    for sensor in (
        lambda: (_ for _ in ()).throw(OSError("OS unavailable")),
        lambda: (_ for _ in ()).throw(NativeIdleUnavailable("no native API")),
    ):
        probe=NativeDragonIdleProbe(
            clock=lambda:NOW+720,monotonic_clock=lambda:1.,
            input_idle_seconds=sensor,host_signals=flags)
        with pytest.raises(NativeIdleUnavailable):
            probe.observe()
    probe=NativeDragonIdleProbe(
        clock=lambda:NOW+720,monotonic_clock=lambda:1.,
        input_idle_seconds=lambda:900.,host_signals=lambda:None)
    with pytest.raises(NativeIdleUnavailable):
        probe.observe()


def test_local_probe_cannot_be_configured_to_accept_bogus_inputs():
    for config in (
        {"maximum_sample_duration":0},
        {"maximum_sample_duration":11},
        {"maximum_trusted_idle_seconds":299},
        {"maximum_trusted_idle_seconds":86401},
    ):
        with pytest.raises(ValueError):
            NativeDragonIdleProbe(
                clock=lambda:NOW,monotonic_clock=lambda:0,
                input_idle_seconds=lambda:900,host_signals=flags,**config)
    with pytest.raises(ValueError):
        NativeDragonIdleProbe(host_signals=None)


def test_wayland_xwayland_never_claims_all_screen_input(monkeypatch):
    monkeypatch.setattr(sys,"platform","linux")
    monkeypatch.setenv("WAYLAND_DISPLAY","wayland-0")
    monkeypatch.setenv("DISPLAY",":1")
    with pytest.raises(NativeIdleUnavailable,match="Wayland"):
        _linux_x11_idle_seconds()
    monkeypatch.delenv("WAYLAND_DISPLAY")
    monkeypatch.delenv("DISPLAY")
    with pytest.raises(NativeIdleUnavailable,match="X11"):
        _linux_x11_idle_seconds()
    monkeypatch.setenv("DISPLAY","localhost:10.0")
    with pytest.raises(NativeIdleUnavailable,match="remote X11"):
        _linux_x11_idle_seconds()
    monkeypatch.setenv("DISPLAY","remote.example.org:0")
    with pytest.raises(NativeIdleUnavailable,match="remote X11"):
        _linux_x11_idle_seconds()


def test_unknown_operating_system_fails_closed(monkeypatch):
    monkeypatch.setattr(sys,"platform","freebsd14")
    with pytest.raises(NativeIdleUnavailable):
        os_input_idle_seconds()


def test_native_idle_probe_can_drive_existing_host_without_network():
    # Host with valid consent, no parent inventory or fetch callbacks:
    # the local OS observer can drive safe zero-work ticks.
    from skeleton.ai.webcrawler.dragon_family_custody_bridge import DragonFamilyCustodyBridge
    from skeleton.ai.webcrawler.dragon_family_idle_host import idle_consent_scope
    from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
    owner="native-host-owner"
    db=sqlite3.connect(":memory:")
    bridge=DragonFamilyCustodyBridge(db,owner)
    host=DragonIdleHostControl(bridge)
    topics=("game_design",)
    scope=idle_consent_scope(owner,topics,())
    grant=DragonConsentLedger(db).issue(owner,capture=True,analysis=True,
        issued_at=NOW+100,expires_at=NOW+4000,
        policy_version="native-activity",scope_digest=scope,authorized=True)
    host.activate(consent_id=grant.consent_id,task_topics=topics,
                  at=NOW+500,authorized=True)
    live=NativeDragonIdleProbe(
        clock=lambda:NOW+720,monotonic_clock=lambda:1.,
        input_idle_seconds=lambda:620.,host_signals=flags)
    observed=host.tick(authorized=True,host_idle_state=live.observe)
    assert observed["attempted"]==0 and observed["changed"]==0
    assert observed["reason"]=="parent_source_quest_incomplete"
    assert host.status(at=NOW+721,authorized=True)["active"]
    db.close()
