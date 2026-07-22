from __future__ import annotations
"""
Model-Harness Training Loop (from the diagram).
Discover Primitive (skills, loops, compactions, ralph loops) -> Add to Harness (standardize) -> Train Next Model (with harness in loop) -> Model Improves -> Cycle repeats.
Absorbs harness primitives into model training for smarter agents.
Integrated into Jeeves/self_systems for CNS game building.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class HarnessPrimitive:
    name: str
    type: str  # skill, loop, compaction, ralph_loop
    description: str
    absorbed: bool = False
    performance_gain: float = 0.0

@dataclass
class ModelHarnessCycle:
    cycle_id: int
    discovered_primitives: List[HarnessPrimitive] = field(default_factory=list)
    harness_updates: List[str] = field(default_factory=list)
    model_improvement: float = 0.0
    status: str = "active"

class ModelHarnessTrainingLoop:
    """
    The Model-Harness Training Loop.
    Primitives (from discover) get absorbed into model training via harness.
    Makes agents smarter by standardizing loops/skills into training.
    Used in idle_training + learning for agent teams in 1000 rooms.
    """

    def __init__(self):
        self.harness: Dict[str, HarnessPrimitive] = {}
        self.cycles: List[ModelHarnessCycle] = []
        self.current_model_performance = 0.5  # Baseline

    def discover_primitive(self, name: str, ptype: str, description: str) -> HarnessPrimitive:
        """Discover Primitive e.g. skills, compactions, ralph loops, loop types."""
        prim = HarnessPrimitive(name=name, type=ptype, description=description)
        self.harness[name] = prim
        return prim

    def add_to_harness(self, prim: HarnessPrimitive) -> str:
        """Add to Harness: standardize into product."""
        if prim.name in self.harness:
            self.harness[prim.name].absorbed = True
            update = f"Standardized {prim.name} ({prim.type}) into harness."
            return update
        return "Primitive not found."

    def train_next_model(self, with_harness: bool = True) -> float:
        """Train Next Model with harness in the loop. Model improves."""
        gain = 0.05 if with_harness else 0.01
        self.current_model_performance += gain
        for name, prim in self.harness.items():
            if prim.absorbed:
                prim.performance_gain += gain
        return self.current_model_performance

    def run_cycle(self, prompt_context: str = "game_building_task") -> ModelHarnessCycle:
        """Full cycle: Discover -> Add -> Train -> Improve. Repeats."""
        cycle_id = len(self.cycles) + 1
        cycle = ModelHarnessCycle(cycle_id=cycle_id)
        
        # Discover (sim: from context or idle_training)
        discovered = [
            HarnessPrimitive(f"loop_{cycle_id}_reasoning", "loop", f"Reasoning loop for {prompt_context}"),
            HarnessPrimitive(f"skill_{cycle_id}_scenebind", "skill", "Multimodal binding primitive"),
            HarnessPrimitive(f"ralph_loop_{cycle_id}", "ralph_loop", "Early exit prevention loop")
        ]
        cycle.discovered_primitives = discovered
        
        for prim in discovered:
            update = self.add_to_harness(prim)
            cycle.harness_updates.append(update)
        
        # Train
        new_perf = self.train_next_model(with_harness=True)
        cycle.model_improvement = new_perf - (new_perf - 0.05)
        
        cycle.status = "completed" if new_perf > 0.8 else "active"
        self.cycles.append(cycle)
        return cycle

    def status(self) -> Dict[str, Any]:
        return {
            "harness_size": len(self.harness),
            "absorbed_primitives": sum(1 for p in self.harness.values() if p.absorbed),
            "current_model_perf": round(self.current_model_performance, 3),
            "cycles_run": len(self.cycles),
            "inspired_by": "Model-Harness Training Loop diagram"
        }
