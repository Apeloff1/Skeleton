"""Godot world emitter (creative longform).
Takes WorldConductor output and emits project.godot, world.tscn, room scripts, boss scene stubs.
"""
from __future__ import annotations
from typing import Any, Dict, List


class GodotWorldEmitter:
    def emit(self, world: Dict[str, Any], brief: str = "AshTunnels") -> Dict[str, Any]:
        if not isinstance(world, dict):
            return {"ok": False, "reason": "bad_world", "room_count": 0}
        if "rooms" in world and not isinstance(world.get("rooms"), list):
            return {"ok": False, "reason": "bad_rooms", "room_count": 0}
        raw_rooms = world.get("rooms", [])
        rooms: List[Dict[str, Any]] = []
        for room in raw_rooms:
            if not isinstance(room, dict):
                continue
            room_id = room.get("id")
            if isinstance(room_id, bool) or not isinstance(room_id, int):
                continue
            rooms.append(room)
        name = (brief.replace(" ", "_")[:32] if isinstance(brief, str) else "") or "AshTunnels"
        project = (
            "[application]\n"
            f'config/name="{name}"\n'
            'run/main_scene="res://world.tscn"\n'
            'config/features=PackedStringArray("4.2", "GL Compatibility")\n\n'
            "[autoload]\n"
            'Jeeves="*res://jeeves/jeeves.gd"\n'
            'Economy="*res://economy/economy.gd"\n'
        )
        room_nodes = []
        for room in rooms:
            room_nodes.append(f'[node name="Room_{room["id"]}" type="Node2D" parent="."]')
            room_nodes.append(f'biome = "{room.get("biome", "ash")}"')
            room_nodes.append(f'difficulty = {room.get("difficulty", 0.5)}')
        tscn = (
            "[gd_scene load_steps=2 format=3]\n"
            '[ext_resource type="Script" path="res://world.gd" id="1"]\n'
            '[node name="World" type="Node2D"]\n'
            'script = ExtResource("1")\n'
            + "\n".join(room_nodes)
        )
        world_gd = (
            "extends Node2D\n"
            "var rooms_cleared: int = 0\n"
            "func _ready() -> void:\n"
            "    print(\"World loaded from conductor\")\n"
            "func on_room_cleared() -> void:\n"
            "    rooms_cleared += 1\n"
            "    if rooms_cleared >= 4:\n"
            "        _spawn_boss()\n"
            "func _spawn_boss() -> void:\n"
            "    var boss = preload(\"res://boss.tscn\").instantiate()\n"
            "    add_child(boss)\n"
        )
        boss_gd = (
            "extends Node2D\n"
            "var phase: int = 0\n"
            "var health: float = 200.0\n"
            "signal defeated\n"
            "func take_damage(amt: float) -> void:\n"
            "    health -= amt\n"
            "    if health <= 0.0:\n"
            "        defeated.emit()\n"
        )
        report = f"# World Emit\nRooms: {len(rooms)}\nDigest: {world.get('digest', 'none')}\n"
        return {
            "ok": True,
            "reason": "ok",
            "room_count": len(rooms),
            "project.godot": project,
            "world.tscn": tscn,
            "world.gd": world_gd,
            "boss.gd": boss_gd,
            "reports/world_emit.md": report,
        }
