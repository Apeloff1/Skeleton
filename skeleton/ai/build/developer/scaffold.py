"""
Skeleton Developer CLI - Scaffold Engine

Provides project templates and scaffolding for:
  - minimal-agent      : Lightweight agent core
  - game-forge         : Game development scaffold
  - swarm-orchestrator : Multi-agent orchestration
  - api-gateway        : REST API service template
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict


TEMPLATES: Dict[str, Dict[str, Any]] = {
    "minimal-agent": {
        "description": "Lightweight agent core with minimal dependencies",
        "files": {
            "agent.py": '''"""Minimal agent implementation."""
from skeleton.forge.universal import Blueprint

class MinimalAgent:
    """A lightweight agent built on Skeleton."""
    def __init__(self):
        self.blueprint = Blueprint()
        self.state = {}

    def act(self, perception: dict) -> dict:
        """Process perception and return action."""
        return {"action": "noop", "confidence": 1.0}
''',
            "main.py": '''"""Entry point for minimal agent."""
from agent import MinimalAgent

if __name__ == "__main__":
    agent = MinimalAgent()
    print("Minimal agent ready.")
''',
            "README.md": """# Minimal Agent

A lightweight agent built on the Skeleton platform.

## Usage

```bash
python main.py
```
""",
        },
    },
    "game-forge": {
        "description": "Game development scaffold with forge integration",
        "files": {
            "game.py": '''"""Game forge scaffold."""
from skeleton.forge.universal import Blueprint

class GameWorld:
    """A game world built from blueprints."""
    def __init__(self):
        self.entities = []
        self.systems = []

    def spawn(self, blueprint: Blueprint):
        """Spawn an entity from a blueprint."""
        self.entities.append(blueprint)
''',
            "main.py": '''"""Entry point for game forge."""
from game import GameWorld

if __name__ == "__main__":
    world = GameWorld()
    print("Game world initialized.")
''',
            "README.md": """# Game Forge

Game development scaffold using Skeleton blueprints.

## Usage

```bash
python main.py
```
""",
        },
    },
    "swarm-orchestrator": {
        "description": "Multi-agent orchestration and coordination",
        "files": {
            "swarm.py": '''"""Swarm orchestrator scaffold."""
from skeleton.forge.universal import Blueprint
from typing import List

class SwarmOrchestrator:
    """Orchestrate multiple agents in a swarm."""
    def __init__(self):
        self.agents: List[Blueprint] = []

    def add_agent(self, agent: Blueprint):
        """Add an agent to the swarm."""
        self.agents.append(agent)

    def broadcast(self, message: dict):
        """Broadcast a message to all agents."""
        for agent in self.agents:
            pass  # Agent processing
''',
            "main.py": '''"""Entry point for swarm orchestrator."""
from swarm import SwarmOrchestrator

if __name__ == "__main__":
    swarm = SwarmOrchestrator()
    print("Swarm ready.")
''',
            "README.md": """# Swarm Orchestrator

Multi-agent orchestration using Skeleton.

## Usage

```bash
python main.py
```
""",
        },
    },
    "api-gateway": {
        "description": "REST API service template with routes",
        "files": {
            "service.py": '''"""API gateway service scaffold."""
from skeleton.api.routes import Router

class GatewayService:
    """A REST API gateway built on Skeleton."""
    def __init__(self):
        self.router = Router()

    def start(self, host="0.0.0.0", port=8000):
        """Start the gateway service."""
        print(f"Gateway starting on {host}:{port}")
''',
            "main.py": '''"""Entry point for API gateway."""
from service import GatewayService

if __name__ == "__main__":
    service = GatewayService()
    service.start()
''',
            "README.md": """# API Gateway

REST API service template using Skeleton routes.

## Usage

```bash
python main.py
```
""",
        },
    },
}

_PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def list_templates() -> Dict[str, Dict[str, Any]]:
    """Return available template metadata."""
    return {key: {"description": value["description"]} for key, value in TEMPLATES.items()}


def _validate_project_name(name: str) -> str:
    """Return a safe single-directory project name or raise ValueError."""
    if name in {".", ".."} or not _PROJECT_NAME.fullmatch(name):
        raise ValueError(
            "project name must be a single path-safe name using letters, numbers, '.', '_' or '-'"
        )
    return name


class ScaffoldEngine:
    """Engine for scaffolding new projects from templates."""

    def __init__(self, output_dir: str | Path = "."):
        self.output_dir = Path(output_dir)

    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        """Return template metadata through the engine API."""
        return list_templates()

    def _project_dir(self, name: str) -> Path:
        safe_name = _validate_project_name(name)
        root = self.output_dir.expanduser().resolve()
        candidate = (root / safe_name).resolve()
        if candidate.parent != root:
            raise ValueError("project path escapes configured output directory")
        return candidate

    def scaffold(self, template: str, name: str, *, force: bool = False) -> Path:
        """Materialize a template and return the created project directory."""
        if template not in TEMPLATES:
            available = ", ".join(sorted(TEMPLATES))
            raise ValueError(f"unknown template {template!r}; available: {available}")

        project_dir = self._project_dir(name)
        if project_dir.is_symlink():
            raise ValueError("refusing to scaffold through a symlinked project path")
        if project_dir.exists() and not force:
            raise FileExistsError(f"directory {str(project_dir)!r} already exists")
        if project_dir.exists() and not project_dir.is_dir():
            raise ValueError("project destination exists and is not a directory")

        project_dir.mkdir(parents=True, exist_ok=True)
        template_spec = TEMPLATES[template]
        for filename, content in template_spec["files"].items():
            target = project_dir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        return project_dir

    def validate_project(self, project_dir: str | Path) -> Dict[str, Any]:
        """Return deterministic structural validation for a generated project."""
        path = Path(project_dir)
        required = ("main.py", "README.md")
        missing = [name for name in required if not (path / name).is_file()]
        python_files = sorted(
            child.relative_to(path).as_posix()
            for child in path.rglob("*.py")
            if child.is_file()
        ) if path.is_dir() else []
        return {
            "valid": path.is_dir() and not missing and bool(python_files),
            "missing": missing,
            "python_files": python_files,
        }

    def create_project(self, template: str, name: str, force: bool = False) -> str:
        """Backward-compatible string-returning wrapper around :meth:`scaffold`."""
        try:
            project_dir = self.scaffold(template, name, force=force)
        except (FileExistsError, ValueError) as exc:
            return str(exc)
        return f"Created '{template}' project at {project_dir}"
