"""Deterministic Godot scene-delta text for one committed fixed step.

Source axes stay X east, Y north, Z up. The emitted transform uses the same
Y-up conversion as the Forge frontier overlay: Godot ``(x, z, -y)``.
"""
from __future__ import annotations

import json
from typing import Mapping


GODOT_SCENE = "frontier/step_delta.tscn"
GODOT_SCRIPT = "frontier/step_delta.gd"


def _num(value: object) -> str:
    return json.dumps(float(value), allow_nan=False)  # type: ignore[arg-type]


def _vec(value: object) -> tuple[float, float, float]:
    x, y, z = value  # type: ignore[misc]
    return float(x), float(y), float(z)


def _godot_origin(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = xyz
    return x, z, -y


def _node(name: str, parent: str, origin: tuple[float, float, float]) -> str:
    gx, gy, gz = _godot_origin(origin)
    where = "." if parent == "." else parent
    return (
        f'[node name="{name}" type="Marker3D" parent="{where}"]\n'
        "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, "
        f"{_num(gx)}, {_num(gy)}, {_num(gz)})\n"
    )


def emit_godot_scene_delta(frame: Mapping[str, object]) -> dict[str, str]:
    """Emit a ``.tscn`` fragment and a GDScript resource from a committed frame.

    ``frame`` must already be the solved step. The same mapping always produces
    the same bytes.
    """
    era = str(frame["engine_era"])
    step_index = int(frame["step_index"])  # type: ignore[arg-type]
    fixed_dt = float(frame["fixed_dt_s"])  # type: ignore[arg-type]
    integrator = str(frame["integrator"])
    lines = [
        "[gd_scene load_steps=2 format=3]",
        "",
        '[ext_resource type="Script" path="res://frontier/step_delta.gd" id="1"]',
        "",
        '[node name="FrontierFixedStep" type="Node3D"]',
        'script = ExtResource("1")',
        "",
    ]
    nodes: list[tuple[str, str]] = []
    channels = frame["channels"]
    if not isinstance(channels, Mapping):
        raise ValueError("committed channels required")
    soft = channels.get("soft_body")
    if isinstance(soft, list):
        for node in soft:
            if not isinstance(node, Mapping):
                continue
            nodes.append((f"Soft_{node['id']}", _node(f"Soft_{node['id']}", ".", _vec(node["xyz"]))))
    weather = channels.get("weather")
    if isinstance(weather, Mapping) and "wind_xyz" in weather:
        nodes.append(("Weather", _node("Weather", ".", _vec(weather["wind_xyz"]))))
    lifecycle = channels.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        for structure in lifecycle.get("structures") or []:
            if isinstance(structure, Mapping):
                # Structures are placed by their committed integrity probe origin.
                origin = _vec(structure.get("xyz", (0.0, 0.0, 0.0)))
                nodes.append((
                    f"Structure_{structure['id']}",
                    _node(f"Structure_{structure['id']}", ".", origin),
                ))
    character = channels.get("character_collision")
    if isinstance(character, Mapping) and character.get("present") is True:
        nodes.append(("Character", _node("Character", ".", _vec(character["position"]))))
    actors = frame.get("actors")
    if isinstance(actors, list):
        for actor in actors:
            if isinstance(actor, Mapping):
                nodes.append((
                    f"Actor_{actor['actor_id']}",
                    _node(f"Actor_{actor['actor_id']}", ".", _vec(actor["position"])),
                ))
    contacts = frame.get("actor_contacts")
    if isinstance(contacts, list):
        for index, contact in enumerate(contacts):
            if not isinstance(contact, Mapping):
                continue
            name = f"Contact_{index:03d}"
            # Contact markers sit at the receiving actor origin already emitted.
            actor_id = str(contact["body_a"])
            origin = (0.0, 0.0, 0.0)
            if isinstance(actors, list):
                for actor in actors:
                    if isinstance(actor, Mapping) and actor.get("actor_id") == actor_id:
                        origin = _vec(actor["position"])
                        break
            block = _node(name, ".", origin)
            block += (
                f"metadata/normal_impulse_ns = {_num(contact['normal_impulse_ns'])}\n"
                f"metadata/friction_impulse_ns = {_num(contact['friction_impulse_ns'])}\n"
                f"metadata/restitution = {_num(contact['restitution'])}\n"
                f"metadata/friction_coefficient = {_num(contact['friction_coefficient'])}\n"
                f"metadata/energy_before_j = {_num(contact['energy_before_j'])}\n"
                f"metadata/energy_after_j = {_num(contact['energy_after_j'])}\n"
                f"metadata/momentum_residual_ns = {_num(contact['momentum_residual_ns'])}\n"
            )
            nodes.append((name, block))
    for _name, block in sorted(nodes):
        lines.append(block)
    scene = "\n".join(lines)
    if not scene.endswith("\n"):
        scene += "\n"
    script = (
        "extends Node\n"
        f"const ERA := {json.dumps(era)}\n"
        f"const STEP := {step_index}\n"
        f"const FIXED_DT := {_num(fixed_dt)}\n"
        f"const INTEGRATOR := {json.dumps(integrator)}\n"
        "func fixed_dt() -> float:\n"
        "\treturn FIXED_DT\n"
        "func integrator_name() -> String:\n"
        "\treturn INTEGRATOR\n"
    )
    return {GODOT_SCENE: scene, GODOT_SCRIPT: script}
