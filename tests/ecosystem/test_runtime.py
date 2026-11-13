"""Runtime adapter tests."""
from skeleton.jeeves.ecosystem.runtime.godot4 import boot, tick, export_manifest

def test_boot_and_tick():
    b = boot({"era": "ash"})
    assert b["ok"] is True
    t = tick({"hp": 100})
    assert t["ticked"] is True

def test_export():
    e = export_manifest([{"path": "project.godot", "content": ""}])
    assert e["ok"] is True
    assert e["count"] == 1
