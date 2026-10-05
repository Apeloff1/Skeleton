"""
Skeleton — Quick Start Guide

This module provides interactive guidance for getting started with the platform.
"""

from __future__ import annotations

from typing import Any, Dict, List


QUICK_START_STEPS: List[Dict[str, Any]] = [
    {
        "step": 1,
        "title": "Install Skeleton",
        "command": "pip install -e .",
        "description": "Install the package in development mode",
    },
    {
        "step": 2,
        "title": "Boot the System",
        "command": "python -m skeleton run",
        "description": "Boot all 7 genesis phases and wire subsystems",
    },
    {
        "step": 3,
        "title": "Check Health",
        "command": "python -m skeleton dev health",
        "description": "Verify all subsystems are healthy",
    },
    {
        "step": 4,
        "title": "Create a Project",
        "command": "python -m skeleton dev scaffold my-game --template game-forge",
        "description": "Generate a new game project from template",
    },
    {
        "step": 5,
        "title": "Run Tests",
        "command": "python -m skeleton test",
        "description": "Execute the full test suite",
    },
    {
        "step": 6,
        "title": "Start API Server",
        "command": "python deploy.py serve --port 8000",
        "description": "Start the REST API server",
    },
    {
        "step": 7,
        "title": "Explore Documentation",
        "command": "python -m skeleton dev docs overview",
        "description": "Show architecture overview",
    },
]

EXAMPLES: List[Dict[str, Any]] = [
    {
        "title": "Boot Genesis and Access Handles",
        "code": """
from skeleton import Genesis

genesis = Genesis(seed=42).boot()
print(f"Wired {len(genesis.handles)} handles")
print(f"Phases: {genesis.report.phases}")

# Access specific subsystems
rag = genesis.get("rag")
mesh = genesis.get("mesh")
fortress = genesis.get("fortress")
        """.strip(),
    },
    {
        "title": "Create and Validate a Blueprint",
        "code": """
from skeleton.forge.universal import Forge

forge = Forge()
bp = forge.new_blueprint("my_game")

# Add components
forge.instantiate(bp, "player", "hero")
forge.instantiate(bp, "enemy_spawner", "spawner")
forge.instantiate(bp, "weapon_forge", "weapons")

# Connect them
bp.connect(("hero", "intent"), ("spawner", "tick"))
bp.connect(("hero", "intent"), ("weapons", "parts"))

# Validate
problems = bp.validate()
print(f"Validation: {'OK' if not problems else problems}")
        """.strip(),
    },
    {
        "title": "Use the Memory Trinity",
        "code": """
from skeleton import Genesis
from skeleton.memory.core import Chunk

genesis = Genesis(seed=42).boot()
trin = genesis.get("trinity")

# Add documents to RAG
trin.rag.add(Chunk(text="Skeleton is an AI game engine", chunk_id="doc-1"))
trin.rag.add(Chunk(text="Blueprints compose game systems", chunk_id="doc-2"))

# Query across all planes
result = trin.query_unified("game engine", top_k_per_tier=3)
print(f"Found {len(result.facts)} facts")
print(f"Combined score: {result.combined_score:.3f}")
        """.strip(),
    },
    {
        "title": "Coordinate Agents in Swarm",
        "code": """
from skeleton import Genesis

genesis = Genesis(seed=42).boot()
mesh = genesis.get("mesh")

# Register agents with capabilities
agent1 = mesh.join({"reasoning", "vision"}, weight=2.0)
agent2 = mesh.join({"reasoning", "nlp"}, weight=1.5)
agent3 = mesh.join({"vision", "control"}, weight=1.0)

# Route task to most capable agent
assigned = mesh.route("reasoning")
print(f"Task assigned to: {assigned.agent_id}")
print(f"Agent load: {assigned.load}")
        """.strip(),
    },
    {
        "title": "Developer CLI Scaffold",
        "code": """
from skeleton.developer.scaffold import ScaffoldEngine

engine = ScaffoldEngine(output_dir="./projects")
result = engine.create_project("minimal-agent", "my-agent", force=True)
print(result)
        """.strip(),
    },
    {
        "title": "Run Health Checks",
        "code": """
from skeleton import Genesis

genesis = Genesis(seed=42).boot()
health = genesis.health()

print(f"Overall: {'HEALTHY' if health['healthy'] else 'DEGRADED'}")
print(f"Phases: {', '.join(health['phases'])}")
print(f"Subsystems: {health['subsystems']}")
print(f"Invariant violations: {health['invariant_violations']}")
        """.strip(),
    },
]


def print_quick_start() -> str:
    """Print the quick start guide."""
    lines = [
        "╔══════════════════════════════════════════════════════════════════════════════╗",
        "║                         SKELETON QUICK START GUIDE                            ║",
        "║                           v16.0 — Tutolage Platform                          ║",
        "╠══════════════════════════════════════════════════════════════════════════════╣",
        "",
        "Getting Started",
        "───────────────",
        "",
    ]
    
    for step in QUICK_START_STEPS:
        lines.append(f"  Step {step['step']}: {step['title']}")
        lines.append(f"    $ {step['command']}")
        lines.append(f"    → {step['description']}")
        lines.append("")
    
    lines.extend([
        "Code Examples",
        "─────────────",
        "",
    ])
    
    for i, example in enumerate(EXAMPLES, 1):
        lines.append(f"  Example {i}: {example['title']}")
        lines.append("  ```python")
        for line in example['code'].split('\n'):
            lines.append(f"  {line}")
        lines.append("  ```")
        lines.append("")
    
    lines.extend([
        "Useful Commands",
        "───────────────",
        "",
        "  python -m skeleton dev list-templates     Show available templates",
        "  python -m skeleton dev wizard             Interactive project builder",
        "  python -m skeleton dev visualize          Blueprint visualization",
        "  python -m skeleton dev extension my_mod     Create subsystem boilerplate",
        "",
        "  python deploy.py boot --serve             Boot + serve API",
        "  python deploy.py test                     Run all tests",
        "  python deploy.py health --verbose         Detailed health check",
        "",
        "API Endpoints (when serving)",
        "─────────────────────────────",
        "",
        "  GET  /api/v1/health                       System health",
        "  GET  /api/v1/genesis                      Boot report",
        "  POST /api/v1/retrieval/query            Multi-plane search",
        "  POST /api/v1/forge/blueprint            Create blueprint (HMAC)",
        "  POST /api/v1/pipeline/npc               Generate NPC",
        "  POST /api/v1/pipeline/game-logic         Design mechanics",
        "",
        "Documentation",
        "─────────────",
        "",
        "  python -m skeleton dev docs overview      Platform overview",
        "  python -m skeleton dev docs genesis       Boot protocol",
        "  python -m skeleton dev docs forge         Blueprint system",
        "  python -m skeleton dev docs swarm         Agent coordination",
        "  python -m skeleton dev docs api          REST API",
        "  python -m skeleton dev docs testing        Test framework",
        "",
        "╚══════════════════════════════════════════════════════════════════════════════╝",
    ])
    
    return "\n".join(lines)


def get_example(title: str) -> str:
    """Get a specific code example by title."""
    for example in EXAMPLES:
        if example["title"].lower() == title.lower():
            return example["code"]
    return f"Example '{title}' not found. Available: {', '.join(e['title'] for e in EXAMPLES)}"
