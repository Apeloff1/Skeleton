"""B024: keyboard/mouse/touch/gamepad share remappable semantic bindings."""
from __future__ import annotations

import json

import pytest

from skeleton.game.presentation.input_actions import Action, ActionMap, Binding, Control, InputContractError, InputState

K = lambda p: Control("keyboard", p)  # noqa: E731


def make_map() -> ActionMap:
    actions = [Action("jump"), Action("move", "axis2d"), Action("zoom", "axis1d"), Action("pause", context="menu")]
    defaults = [
        Binding("jump", K("key.space")),
        Binding("jump", Control("gamepad", "button.south")),
        Binding("jump", Control("touch", "tap")),
        Binding("jump", Control("mouse", "button.right")),
        Binding("move", K("key.d"), scale=1.0, axis="x"),
        Binding("move", K("key.a"), scale=-1.0, axis="x"),
        Binding("move", K("key.w"), scale=1.0, axis="y"),
        Binding("move", Control("gamepad", "stick.left.x"), axis="x", deadzone=0.2),
        Binding("move", Control("gamepad", "stick.left.y"), axis="y", deadzone=0.2),
        Binding("zoom", Control("mouse", "wheel.y")),
        Binding("zoom", Control("touch", "pinch")),
        Binding("pause", K("key.space")),  # same key, other context: allowed
    ]
    return ActionMap(actions, defaults)


def test_all_four_devices_drive_same_action():
    m = make_map()
    assert m.devices_for("jump") == ("gamepad", "keyboard", "mouse", "touch")
    for ctl in ["keyboard:key.space", "gamepad:button.south", "touch:tap", "mouse:button.right"]:
        s = InputState(m)
        s.feed(ctl, 1.0)
        s.update()
        assert s.value("jump") is True and s.pressed("jump")


def test_pressed_released_edges():
    s = InputState(make_map())
    s.feed("keyboard:key.space", 1); s.update()
    assert s.pressed("jump")
    s.update()
    assert s.value("jump") and not s.pressed("jump")
    s.feed("keyboard:key.space", 0); s.update()
    assert s.released("jump")


def test_composite_and_stick_axis_with_deadzone():
    s = InputState(make_map())
    s.feed("keyboard:key.a", 1); s.feed("keyboard:key.w", 1); s.update()
    assert s.value("move") == (-1.0, 1.0)
    s2 = InputState(make_map())
    s2.feed("gamepad:stick.left.x", 0.1); s2.feed("gamepad:stick.left.y", 0.5); s2.update()
    assert s2.value("move") == (0.0, 0.5)


def test_transient_controls_reset_each_frame():
    s = InputState(make_map())
    s.feed("mouse:wheel.y", -0.5); s.update()
    assert s.value("zoom") == -0.5
    s.update()
    assert s.value("zoom") == 0.0


def test_inactive_context_ignored():
    s = InputState(make_map())
    s.feed("keyboard:key.space", 1); s.update()
    assert s.value("pause") is False
    s2 = InputState(make_map(), active_contexts=frozenset({"menu"}))
    s2.feed("keyboard:key.space", 1); s2.update()
    assert s2.value("pause") is True and s2.value("jump") is False


def test_rebind_and_conflict_is_atomic():
    m = make_map()
    m.rebind("jump", K("key.space"), K("key.j"))
    s = InputState(m); s.feed("keyboard:key.j", 1); s.update()
    assert s.value("jump")
    before = m.bindings()
    with pytest.raises(InputContractError, match="conflict"):
        m.rebind("jump", K("key.j"), K("key.d"))  # d is move's
    assert m.bindings() == before


def test_modifier_chord():
    m = make_map()
    m.bind(Binding("jump", K("key.d"), modifiers=("shift",)))  # shift+d ≠ d
    s = InputState(m); s.feed("keyboard:key.d", 1); s.update()
    assert s.value("jump") is False
    s.feed("keyboard:key.shift", 1); s.update()
    assert s.value("jump") is True


def test_export_import_roundtrip_and_reset():
    m = make_map()
    m.rebind("jump", K("key.space"), K("key.j"))
    data = json.loads(json.dumps(m.export_overrides()))
    m2 = make_map(); m2.import_overrides(data)
    assert m2.bindings() == m.bindings()
    m2.reset()
    assert m2.bindings() == make_map().bindings()


def test_import_bad_overrides_all_or_nothing():
    m = make_map()
    before = m.bindings()
    with pytest.raises(InputContractError):
        m.import_overrides({"jump": [{"control": "keyboard:key.j"}], "nope": []})
    with pytest.raises(InputContractError):
        m.import_overrides({"jump": [{"control": "keyboard:key.d"}]})
    assert m.bindings() == before


@pytest.mark.parametrize("dev,path", [("keyboard", "space"), ("gamepad", "button.x"), ("mouse", "button.left; rm"), ("vr", "a"), ("touch", "tap.x")])
def test_invalid_controls(dev, path):
    with pytest.raises(InputContractError):
        Control(dev, path)


def test_invalid_bindings():
    with pytest.raises(InputContractError):
        Binding("jump", Control("gamepad", "button.south"), modifiers=("shift",))
    with pytest.raises(InputContractError):
        Binding("jump", K("key.a"), scale=0)
    with pytest.raises(InputContractError):
        ActionMap([Action("a")], [Binding("b", K("key.a"))])
    with pytest.raises(InputContractError):
        InputState(make_map()).feed("keyboard:key.a", float("nan"))


def test_infinite_device_sample_is_not_treated_as_a_valid_button():
    with pytest.raises(InputContractError):
        InputState(make_map()).feed("keyboard:key.space", float("inf"))


def test_bad_import_row_fails_atomically_instead_of_silently_dropping():
    m = make_map()
    before = m.export_overrides()
    for payload in ({"jump": [None]}, {"jump": [{"control": "keyboard:key.j", "bogus": 1}]},
                    {"jump": [{"control": "keyboard:key.j", "scale": "not-a-number"}]}):
        with pytest.raises(InputContractError):
            m.import_overrides(payload)
        assert m.export_overrides() == before
