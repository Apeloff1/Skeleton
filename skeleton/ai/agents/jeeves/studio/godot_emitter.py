"""Advanced Godot emitter.
Era and mode headers, boss phase, ending, and optical uniforms. Install-safe.
"""
from typing import Any, Dict

class GodotEmitter:
    def emit(self, era: str, mode: str, boss_phase: str, ending: str, optical: float) -> Dict[str, str]:
        if not isinstance(optical, (int, float)) or optical < 0 or optical > 1:
            optical = 0.93
        return {
            "project.godot": f"[application]\nconfig/name=\"Ash Tunnels {era}\"\n; mode={mode} optical={optical}",
            "world.tscn": f"[node name=\"World\" type=\"Node2D\"]\n; era={era} mode={mode}",
            "player.gd": f"var optical = {optical}\nfunc _physics_process(delta):\n\tposition.x += 10 * delta",
            "boss.gd": f"var phase = \"{boss_phase}\"\nvar optical = {optical}\nfunc take_damage(amount):\n\tpass",
            "cutscene_director.gd": f"var ending = \"{ending}\"\nfunc play():\n\tpass",
        }
