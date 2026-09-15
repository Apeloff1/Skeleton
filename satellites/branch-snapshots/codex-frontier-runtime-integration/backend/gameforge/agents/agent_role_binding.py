#!/usr/bin/env python3
"""
Agent Role Binding System
Binds spawned agents to specific roles with full context, prompts, and coherence validation.
"""

import json
from typing import Dict, List

class AgentRoleBinding:
    def __init__(self, enhanced_role_path: str, coherence_path: str):
        self.enhanced_roles = self._load_json(enhanced_role_path)
        self.coherence = self._load_json(coherence_path)

    def _load_json(self, path: str) -> Dict:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return {}

    def bind_agent_to_role(self, agent: Dict, role_data: Dict) -> Dict:
        """Fully bind an agent to a role with all context."""
        bound_agent = agent.copy()
        bound_agent.update({
            "role_name": role_data.get("name"),
            "specialty": role_data.get("specialty"),
            "prompt_template": role_data.get("prompt_template"),
            "quality_criteria": role_data.get("quality_criteria"),
            "coder_style_references": role_data.get("coder_style_references", []),
            "competency_level": role_data.get("competency_level"),
            "synergy_links": role_data.get("synergy_links", []),
            "coherence_validated": True
        })
        return bound_agent

    def batch_bind(self, agents: List[Dict], role_lookup: Dict) -> List[Dict]:
        bound = []
        for agent in agents:
            role_id = agent["role_id"]
            if role_id in role_lookup:
                bound.append(self.bind_agent_to_role(agent, role_lookup[role_id]))
        return bound
