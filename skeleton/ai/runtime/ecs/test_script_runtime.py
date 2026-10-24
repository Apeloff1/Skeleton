"""B023: capability grants, quotas, diagnostics and hot-reload boundaries."""
from __future__ import annotations

import pytest

from skeleton.ai.runtime.ecs.script import ScriptLimits
from skeleton.ai.runtime.ecs.script_runtime import (
    CapabilityError,
    CapabilityRegistry,
    QuotaExceededError,
    ScriptHost,
    ScriptQuarantinedError,
    ScriptQuota,
)
from skeleton.simulation.ecs.errors import ScriptLimitError, ScriptRuntimeError, ScriptValidationError


def make_host(**kw):
    reg = CapabilityRegistry()
    sounds: list[str] = []
    reg.register("ecs.read", "hp_of", lambda e: 10)
    reg.register("audio.play", "play", lambda s: sounds.append(s))
    return ScriptHost(reg, **kw), sounds


def test_granted_capability_is_visible():
    host, sounds = make_host()
    host.load("a", "def f():\n    play('boom')\n    return hp_of(1)\n", grants=["ecs.read", "audio.play"])
    assert host.call("a", "f").value == 10
    assert sounds == ["boom"]


def test_ungranted_capability_is_not_exposed():
    host, sounds = make_host()
    host.load("a", "def f():\n    play('boom')\n", grants=["ecs.read"])
    with pytest.raises(ScriptRuntimeError):
        host.call("a", "f")
    assert sounds == []


@pytest.mark.parametrize("cap", ["unknown.cap", "Bad", "noperiod", ""])
def test_unknown_or_invalid_grant_fails_closed(cap):
    host, _ = make_host()
    with pytest.raises(CapabilityError):
        host.load("a", "x = 1\n", grants=[cap])


def test_registry_rejects_name_collision_across_capabilities():
    reg = CapabilityRegistry()
    reg.register("ecs.read", "get", lambda: 1)
    with pytest.raises(CapabilityError):
        reg.register("ecs.write", "get", lambda: 2)


@pytest.mark.parametrize("src", ["import os\n", "eval('1')\n", "open('/etc/passwd')\n", "x = ().__class__\n"])
def test_unsafe_source_rejected_and_logged(src):
    host, _ = make_host()
    with pytest.raises(ScriptValidationError):
        host.load("bad", src)
    d = host.diagnostics("bad")
    assert d and d[0]["kind"] == "validation" and d[0]["context"]["violations"]


def test_call_quota_quarantines():
    host, _ = make_host()
    host.load("a", "def f():\n    return 1\n", quota=ScriptQuota(max_calls=2))
    host.call("a", "f"); host.call("a", "f")
    with pytest.raises(QuotaExceededError):
        host.call("a", "f")
    with pytest.raises(ScriptQuarantinedError):
        host.call("a", "f")
    assert host.status("a")["quarantined"]


def test_step_limit_counts_as_fault_and_quarantines():
    host, _ = make_host(limits=ScriptLimits(max_steps=1000))
    host.load("a", "def f():\n    while True:\n        pass\n", quota=ScriptQuota(max_faults=2))
    for _ in range(2):
        with pytest.raises(ScriptLimitError):
            host.call("a", "f")
    with pytest.raises(ScriptQuarantinedError):
        host.call("a", "f")
    kinds = [d["kind"] for d in host.diagnostics("a")]
    assert kinds.count("limit") == 2 and "quarantine" in kinds


def test_total_step_quota():
    host, _ = make_host()
    host.load("a", "def f():\n    t = 0\n    for i in range(200):\n        t += i\n    return t\n", quota=ScriptQuota(max_total_steps=300))
    host.call("a", "f")
    host.call("a", "f")
    assert host.status("a")["quarantined"]


def test_hot_reload_carries_only_persistent_plain_state():
    host, _ = make_host()
    host.load("a", "count = 7\nother = 5\ndef f():\n    return count\n", persistent=["count"])
    assert host.reload("a", "count = 99\nother = 1\ndef f():\n    return count * 10 + other\n") == 2
    assert host.call("a", "f").value == 71
    assert host.diagnostics("a")[-1]["kind"] == "reload"
    assert host.diagnostics("a")[-1]["context"]["carried"] == ["count"]


def test_failed_reload_keeps_previous_generation_live():
    host, _ = make_host()
    host.load("a", "def f():\n    return 1\n")
    with pytest.raises(ScriptValidationError):
        host.reload("a", "import os\ndef f():\n    return 2\n")
    assert host.call("a", "f").value == 1
    assert host.status("a")["generation"] == 1
    assert host.diagnostics("a")[-1]["kind"] == "reload_rejected"


def test_reload_clears_quarantine():
    host, _ = make_host()
    host.load("a", "def f():\n    return 1\n", quota=ScriptQuota(max_calls=1))
    host.call("a", "f")
    with pytest.raises(QuotaExceededError):
        host.call("a", "f")
    host.reload("a", "def f():\n    return 2\n")
    assert host.call("a", "f").value == 2


def test_reload_same_source_is_noop():
    host, _ = make_host()
    host.load("a", "def f():\n    return 1\n")
    assert host.reload("a", "def f():\n    return 1\n") == 1


def test_duplicate_load_and_unknown_script():
    host, _ = make_host()
    host.load("a", "x = 1\n")
    with pytest.raises(ScriptRuntimeError):
        host.load("a", "x = 1\n")
    with pytest.raises(ScriptRuntimeError):
        host.call("nope", "f")


def test_diagnostics_bounded():
    from skeleton.ai.runtime.ecs import script_runtime as sr
    host, _ = make_host()
    for i in range(sr.MAX_DIAGNOSTICS + 10):
        with pytest.raises(ScriptValidationError):
            host.load(f"b{i}", "import os\n")
    assert len(host.diagnostics()) == sr.MAX_DIAGNOSTICS
