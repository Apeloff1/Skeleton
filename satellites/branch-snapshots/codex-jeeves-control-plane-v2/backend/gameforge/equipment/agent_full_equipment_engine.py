#!/usr/bin/env python3
"""
Agent Full Equipment Engine
Ensures every agent is fully equipped with:
- Complete role data + coder style references
- Prompt template + quality criteria
- Access to relevant indexes and RAG
- Performance tracking
- Exocortex context access (especially for high-level agents and Judge)
"""

import json
from typing import Dict
from datetime import datetime

class AgentFullEquipmentEngine:
    def __init__(self):
        self.equipped_agents = {}

    def fully_equip_agent(self, agent_id: str, role_data: Dict, room_id: str, 
                          mastery_level: int, exocortex_access: bool = False) -> Dict:
        """Equip a single agent with everything it needs to perform at high level."""
        
        agent = {
            "agent_id": agent_id,
            "room_id": room_id,
            "role_id": role_data.get("role_id"),
            "name": role_data.get("name"),
            "mastery_level": mastery_level,
            "equipped_at": datetime.now().isoformat(),
            "status": "fully_equipped",
            
            # Core Capabilities
            "prompt_template": role_data.get("prompt_template"),
            "quality_criteria": role_data.get("quality_criteria", []),
            "coder_style_references": role_data.get("coder_style_references", []),
            "specialty": role_data.get("specialty"),
            
            # Tools & Access
            "tools": {
                "hybrid_rag": True,
                "category_index": True,
                "role_contribution_graph": True,
                "bookshelf_access": True,
                "exocortex_context": exocortex_access
            },
            
            # Performance & Learning
            "performance_metrics": {
                "coherence_score": 0.0,
                "synergy_contribution": 0.0,
                "task_quality": 0.0,
                "improvement_rate": 0.0
            },
            
            "learning_state": {
                "reflections": [],
                "successful_patterns": [],
                "areas_for_improvement": []
            },
            
            "equipment_version": "1.0"
        }
        
        # Special handling for Judge Agent
        if role_data.get("role_id") == "judge_agent_jeeves":
            agent["exocortex_access"] = {
                "enabled": True,
                "memory_systems": True,
                "journals": True,
                "salience_network": True,
                "coherence_metrics": True
            }
            agent["special_privileges"] = ["tiebreak_voting", "exocortex_judgement"]
        
        self.equipped_agents[agent_id] = agent
        return agent

    def equip_batch(self, agents_data: list, role_lookup: Dict) -> list:
        """Equip multiple agents at once."""
        equipped = []
        for data in agents_data:
            role_data = role_lookup.get(data["role_id"], {})
            agent = self.fully_equip_agent(
                data["agent_id"],
                role_data,
                data["room_id"],
                data.get("mastery_level", 3),
                exocortex_access=(data["role_id"] == "judge_agent_jeeves")
            )
            equipped.append(agent)
        return equipped

if __name__ == "__main__":
    engine = AgentFullEquipmentEngine()
    print("Agent Full Equipment Engine ready. Every agent can now be fully equipped.")
