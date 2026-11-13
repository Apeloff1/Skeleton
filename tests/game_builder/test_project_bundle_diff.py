import json

from skeleton.forge.creator.design_graph import build_design_graph
from skeleton.ai.game_builder.project_bundle.project_diff import DESIGN_GRAPH_PATH, diff_sequences

from .conftest import edit


def graph(label):
    g = build_design_graph(project_id="hero", edges=[],
                           nodes=[{"id": "jump", "kind": "mechanic", "label": label, "attributes": {}}])
    return json.dumps(g.to_payload())


def test_file_diff_between_sequences(saver):
    saver.save_files("hero", "platformer", {"a.md": "1", "b.md": "1"})
    saver.save_files("hero", "platformer", {"a.md": "2", "c.md": "1"})
    d = diff_sequences(saver, "hero", 1, 2)["files"]
    assert (d["added"], d["removed"], d["changed"]) == (["c.md"], ["b.md"], ["a.md"])
    assert diff_sequences(saver, "hero", 2, 2)["files"]["changed"] == []


def test_design_diff_optional(saver):
    saver.save_files("hero", "platformer", {DESIGN_GRAPH_PATH: graph("Jump")})
    saver.save_files("hero", "platformer", {DESIGN_GRAPH_PATH: graph("Double jump")})
    saver.save_files("hero", "platformer", {"a.md": "x"})
    out = diff_sequences(saver, "hero", 1, 2, design=True)
    assert out["files"]["changed"] == [DESIGN_GRAPH_PATH] and out["design"]["changes"]
    assert diff_sequences(saver, "hero", 2, 3, design=True)["design"] is None


def test_workspace_edit_shows_in_diff(ws, saver):
    saver.save_project(ws, "hero")
    edit(ws, "hero", "notes/n.md", "hi")
    saver.save_project(ws, "hero")
    assert diff_sequences(saver, "hero", 1, 2)["files"]["added"] == ["notes/n.md"]
