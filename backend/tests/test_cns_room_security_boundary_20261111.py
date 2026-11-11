"""Boundary tests: optional CNS imports cannot become admin authority."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from routes import gameforge_studio as studio


def test_studio_has_mandatory_auth_dependency_without_unauthorized_fallback():
    tree = ast.parse(Path(studio.__file__).read_text(encoding="utf-8"))
    imports = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "routes.gameforge_auth"
        and any(alias.name == "require_role" for alias in node.names)
    ]
    assert imports, "auth import must execute outside optional CNS try blocks"
    assert studio._editor is not studio._admin
    assert callable(studio._editor)
    assert callable(studio._admin)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == "_editor":
            pytest.fail("local fallback editor/admin principal must never be defined")


class _RoomActivity:
    def __init__(self):
        self.items = []

    def insert_one(self, item):
        self.items.append(item)


class _FakeSteps:
    def __init__(self):
        self.notes = []

    def add_agent_note(self, note):
        self.notes.append(note)


@pytest.fixture
def studio_room(monkeypatch):
    activity = _RoomActivity()
    steps = _FakeSteps()
    monkeypatch.setattr(studio, "_db", lambda: {"gameforge_room_activity": activity})
    monkeypatch.setattr(studio, "_room_ids", lambda: ["room_a", "room_b", "room_c"])
    monkeypatch.setattr(studio, "get_step_database", lambda _id: steps)
    monkeypatch.setitem(studio._rr, "i", 0)
    return activity, steps


def test_sensitive_room_data_is_redacted_before_storage_and_agent_notes(studio_room):
    activity, steps = studio_room
    payload = {
        "step_id": "intro",
        "authorization": "Bearer private-credential",
        "nested": {
            "api_key": "private-credential",
            "url": "https://api.test/?token=private-credential&safe=yes",
        },
        "status": "accepted",
    }
    selected = studio.dispatch_to_rooms("step.accept", payload, fanout=2)
    assert selected == ["room_a", "room_b"]
    assert len(activity.items) == 1
    item = activity.items[0]
    assert item["payload"]["authorization"] == "[REDACTED]"
    assert item["payload"]["nested"]["api_key"] == "[REDACTED]"
    assert "private-credential" not in str(item)
    assert item["payload"]["status"] == "accepted"
    assert len(steps.notes) == 1
    assert "private-credential" not in steps.notes[0]
    assert "activity recorded" in steps.notes[0]


def test_room_dispatch_never_stringifies_untrusted_objects(studio_room):
    activity, _steps = studio_room

    class Secret:
        def __repr__(self):
            raise AssertionError("repr is not an approved shared-room field")

        def __str__(self):
            raise AssertionError("str is not an approved shared-room field")

    studio.dispatch_to_rooms("safe", {"danger": Secret()})
    assert activity.items[0]["payload"]["danger"] == "[UNSUPPORTED]"


@pytest.mark.parametrize("event,payload,fanout", [
    ("", {}, 1),
    ("a" * 81, {}, 1),
    ("ok", [], 1),
    ("ok", {}, 1.5),
    ("ok", {}, True),
    ("ok", {}, -1),
    ("ok", {}, 1001),
])
def test_room_dispatch_rejects_unbounded_or_noncanonical_inputs(
    studio_room, event, payload, fanout,
):
    with pytest.raises(ValueError):
        studio.dispatch_to_rooms(event, payload, fanout=fanout)
    assert studio_room[0].items == []


def test_room_dispatch_rejects_oversized_nested_payload_before_mongo(studio_room):
    with pytest.raises(ValueError, match="byte budget"):
        studio.dispatch_to_rooms(
            "note",
            {"large": ["x" * 1900 for _ in range(50)]},
            fanout=3,
        )
    assert studio_room[0].items == []


def test_room_dispatch_zero_fanout_still_has_bounded_log(studio_room):
    selected = studio.dispatch_to_rooms("save", {"status": "ok"}, fanout=0)
    assert selected == []
    assert studio_room[0].items[0]["rooms"] == []
