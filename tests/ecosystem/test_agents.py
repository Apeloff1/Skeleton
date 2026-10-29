"""Agent toolkit smoke tests."""
from skeleton.jeeves.ecosystem.agents.code_writer import run as code_run
from skeleton.jeeves.ecosystem.agents.level_designer import LeveldesignerAgent

def test_code_writer():
    r = code_run("platformer", era="ash")
    assert r["ok"] is True
    assert r["agent"] == "code_writer"

def test_level_designer():
    a = LeveldesignerAgent(era="NES", optical=0.96)
    r = a.build_graph("dungeon")
    assert r["ok"] is True
    assert r["era"] == "NES"
