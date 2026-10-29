"""Godot world emitter (creative longform).
Takes WorldConductor output and emits project.godot, world.tscn, room scripts, boss scene stubs.
"""
from __future__ import annotations
from typing import Any, Dict, List

class GodotWorldEmitter:
    def emit(self, world: Dict[str, Any], brief: str = "AshTunnels") -> Dict[str, str]:
        name = brief.replace(" ", "_")[:32] or "AshTunnels"
        project = f"""[application]\nconfig/name=\"{name}\"\nrun/main_scene=\"res://world.tscn\"\nconfig/features=PackedStringArray(\"4.2\", \"GL Compatibility\")\n\n[autoload]\nJeeves=\"*res://jeeves/jeeves.gd\"\nEconomy=\"*res://economy/economy.gd\"\n"""
        rooms = world.get("rooms", [])
        room_nodes = []
        for r in rooms[:6]:
            room_nodes.append(f'[node name=\"Room_{r["id\"]}\" type=\"Node2D\" parent=\".\"]')
            room_nodes.append(f'biome = \"{r.get(\"biome\", \"ash\")}\"')
            room_nodes.append(f'difficulty = {r.get(\"difficulty\", 0.5)}')
        tscn = """[gd_scene load_steps=2 format=3]\n[ext_resource type=\"Script\" path=\"res://world.gd\" id=\"1\"]\n[node name=\"World\" type=\"Node2D\"]\nscript = ExtResource(\"1\")\n""" + "\\n".join(room_nodes)
        world_gd = """extends Node2D\nvar rooms_cleared: int = 0\nfunc _ready() -> void:\n    print(\"World loaded from conductor\")\nfunc on_room_cleared() -> void:\n    rooms_cleared += 1\n    if rooms_cleared >= 4:\n        _spawn_boss()\nfunc _spawn_boss() -> void:\n    var boss = preload(\"res://boss.tscn\").instantiate()\n    add_child(boss)\n"""
        boss_gd = """extends Node2D\nvar phase: int = 0\nvar health: float = 200.0\nsignal defeated\nfunc take_damage(amt: float) -> void:\n    health -= amt\n    if health <= 0.0:\n        defeated.emit()\n"""
        return {
            "project.godot": project,
            "world.tscn": tscn,
            "world.gd": world_gd,
            "boss.gd": boss_gd,
            "reports/world_emit.md": f"# World Emit\\nRooms: {len(rooms)}\\nDigest: {world.get('digest', 'none')}\\n",
        }
