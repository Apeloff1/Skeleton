"""
Skeleton Developer CLI — Core scaffolding engine

Provides:
- Project template generation
- Subsystem scaffolding
- Interactive wizard support
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ScaffoldTemplate:
    """A reusable project template."""
    name: str
    description: str
    files: Dict[str, str] = field(default_factory=dict)
    directories: List[str] = field(default_factory=list)
    post_hooks: List[str] = field(default_factory=list)


class TemplateLibrary:
    """Built-in templates for common Skeleton projects."""

    @staticmethod
    def minimal_agent() -> ScaffoldTemplate:
        return ScaffoldTemplate(
            name="minimal-agent",
            description="Single-agent project with memory and reasoning",
            directories=["src", "tests", "config"],
            files={
                "src/agent.py": '"""Minimal Skeleton agent."""\nfrom skeleton import Genesis\n\nclass MinimalAgent:\n    def __init__(self):\n        self.genesis = Genesis(seed=42).boot()\n        self.memory = self.genesis.get("rag")\n        self.orchestrator = self.genesis.get("orchestrator")\n\n    def think(self, query: str) -> str:\n        """Reason over memory and return a response."""\n        context = self.memory.query(query, k=3)\n        return self.orchestrator.reason(query=query, context=context)\n',
                "tests/test_agent.py": '"""Tests for minimal agent."""\nfrom skeleton.testing.scaffold import TestCase\nfrom src.agent import MinimalAgent\n\nclass TestMinimalAgent(TestCase):\n    def setUp(self):\n        self.agent = MinimalAgent()\n\n    def test_think_returns_string(self):\n        result = self.agent.think("hello")\n        self.assertIsInstance(result, str)\n',
                "config/settings.yaml": '# Minimal agent configuration\nmemory:\n  rag_k: 3\n  cag_enabled: false\n\norchestrator:\n  max_reasoning_depth: 5\n',
                "README.md": '# Minimal Agent\n\nA single-agent Skeleton project.\n\n## Quick Start\n\n```bash\npython -m skeleton dev run\n```\n',
            },
        )

    @staticmethod
    def game_forge_project() -> ScaffoldTemplate:
        return ScaffoldTemplate(
            name="game-forge",
            description="Game development project with forge pipeline",
            directories=["src", "assets", "scenes", "tests", "scripts"],
            files={
                "src/game.py": '"""Game forge project."""\nfrom skeleton.forge.universal import Forge, Blueprint\nfrom skeleton.forge.eras import compile_era\n\nclass GameProject:\n    def __init__(self, era="extraction_now"):\n        self.forge = Forge()\n        self.era = compile_era(era)\n\n    def build_player(self) -> Blueprint:\n        bp = self.forge.new_blueprint("player")\n        self.forge.instantiate(bp, "player", "hero")\n        self.forge.instantiate(bp, "weapon_forge", "gear")\n        bp.connect(("hero", "intent"), ("gear", "parts"))\n        return bp\n',
                "tests/test_game.py": '"""Game project tests."""\nfrom skeleton.testing.scaffold import TestCase\nfrom src.game import GameProject\n\nclass TestGameProject(TestCase):\n    def test_build_player(self):\n        game = GameProject()\n        bp = game.build_player()\n        self.assertEqual(len(bp.components), 2)\n',
                "scripts/build.sh": '#!/bin/bash\nset -e\necho "Building game project..."\npython -m skeleton forge materialise --target godot\n',
            },
        )

    @staticmethod
    def swarm_orchestrator() -> ScaffoldTemplate:
        return ScaffoldTemplate(
            name="swarm-orchestrator",
            description="Multi-agent swarm with negotiation",
            directories=["src/agents", "src/coordination", "tests", "config"],
            files={
                "src/coordination/hive.py": '"""Swarm coordination."""\nfrom skeleton import Genesis\nfrom skeleton.swarm import SwarmMesh\n\nclass HiveCoordinator:\n    def __init__(self, agent_count=3):\n        self.genesis = Genesis(seed=42).boot()\n        self.mesh = self.genesis.get("mesh")\n        self.negotiator = self.genesis.get("negotiator")\n        self._spawn_agents(agent_count)\n\n    def _spawn_agents(self, count: int):\n        for i in range(count):\n            self.mesh.join(\n                specialisations={"reasoning", "memory"},\n                weight=1.0,\n                metadata={"id": f"agent_{i}"}\n            )\n\n    def delegate(self, task: str) -> str:\n        agent = self.mesh.route("reasoning")\n        return f"Task \'{task}\' delegated to {agent.agent_id}"\n',
                "tests/test_hive.py": '"""Swarm tests."""\nfrom skeleton.testing.scaffold import TestCase\nfrom src.coordination.hive import HiveCoordinator\n\nclass TestHiveCoordinator(TestCase):\n    def test_delegation(self):\n        hive = HiveCoordinator(agent_count=2)\n        result = hive.delegate("analyze data")\n        self.assertIn("delegated", result)\n',
            },
        )

    @classmethod
    def all_templates(cls) -> List[ScaffoldTemplate]:
        return [
            cls.minimal_agent(),
            cls.game_forge_project(),
            cls.swarm_orchestrator(),
        ]


class ScaffoldEngine:
    """Generates projects from templates."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.library = TemplateLibrary()

    def list_templates(self) -> List[Dict[str, str]]:
        return [
            {"name": t.name, "description": t.description}
            for t in self.library.all_templates()
        ]

    def scaffold(self, template_name: str, project_name: str, target_dir: Optional[Path] = None) -> Path:
        template = next((t for t in self.library.all_templates() if t.name == template_name), None)
        if template is None:
            raise ValueError(f"Unknown template: {template_name}")

        dest = Path(target_dir or self.root) / project_name
        if dest.exists():
            raise FileExistsError(f"Project directory already exists: {dest}")

        dest.mkdir(parents=True)

        for directory in template.directories:
            (dest / directory).mkdir(parents=True, exist_ok=True)

        for path, content in template.files.items():
            file_path = dest / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content.strip() + "\n")
            if path.endswith(".sh"):
                file_path.chmod(0o755)

        return dest

    def validate_project(self, project_dir: Path) -> Dict[str, Any]:
        """Check a project for Skeleton conventions."""
        results = {
            "has_src": (project_dir / "src").exists(),
            "has_tests": (project_dir / "tests").exists(),
            "has_config": (project_dir / "config").exists(),
            "has_readme": (project_dir / "README.md").exists(),
            "skeleton_imports": [],
        }

        for py_file in project_dir.rglob("*.py"):
            content = py_file.read_text()
            if "from skeleton" in content or "import skeleton" in content:
                results["skeleton_imports"].append(str(py_file.relative_to(project_dir)))

        return results
