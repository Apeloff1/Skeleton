import pytest
from full_proto.jeeves.full_tutor import FullJeevesTutor
from full_proto.godot.full_emitter import FullGodotEmitter
from pathlib import Path
import tempfile

def test_jeeves_full():
    t = FullJeevesTutor()
    sid = t.start("tester")
    res = t.respond(sid, "build a solar roguelite")
    assert res["quality_score"] > 0.9
    assert res["laws_satisfied"]

def test_godot_emit():
    e = FullGodotEmitter()
    with tempfile.TemporaryDirectory() as tmp:
        res = e.emit({"title": "Test"}, Path(tmp))
        assert res["ok"]
        assert (Path(tmp) / "world.tscn").exists()
