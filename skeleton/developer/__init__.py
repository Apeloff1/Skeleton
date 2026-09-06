"""
Skeleton Developer CLI — Main entry point and integration

Provides:
- skeleton dev <command> main entry
- Integration with existing __main__.py
- Documentation and help system
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def dev_help_text() -> str:
    return """
===============================================================================
                        SKELETON DEVELOPER CLI
                         v16.0 — Skeleton Codename
===============================================================================

  DEVELOPMENT COMMANDS

    skeleton dev scaffold <name> [options]
        Generate a new project from a template
        --template, -t    Template name (minimal-agent, game-forge, swarm-orchestrator)
        --dir, -d         Target directory (default: current)
        --dry-run         Preview without creating files

    skeleton dev wizard [options]
        Interactive project creation wizard
        --answers         JSON string of pre-filled answers
        --non-interactive Use all defaults

    skeleton dev health [options]
        Subsystem health dashboard
        --json            Output as JSON
        --watch, -w       Continuous monitoring
        --interval        Watch interval in seconds (default: 5)

    skeleton dev visualize [options]
        Blueprint and topology visualization
        --blueprint, -b   Blueprint name to visualize
        --topology, -t    Show as JSON topology
        --compact, -c     Compact text output
        --save, -s        Save output to file

    skeleton dev extension <name> [options]
        Generate boilerplate for new subsystems
        --type            Extension type (subsystem, pipeline, agent, tool)
        --with-tests      Generate tests (default: true)
        --with-api        Generate API routes

  UTILITY COMMANDS

    skeleton dev list-templates
        Show all available project templates

    skeleton dev validate <path>
        Validate a Skeleton project for conventions

    skeleton dev docs [topic]
        Show documentation for a subsystem or topic

  EXAMPLES

    # Create a new agent project
    skeleton dev scaffold my-agent --template minimal-agent

    # Run interactive wizard
    skeleton dev wizard

    # Check all subsystem health
    skeleton dev health

    # Visualize a blueprint
    skeleton dev visualize --blueprint player --save player.txt

    # Create a new subsystem extension
    skeleton dev extension my_feature --type subsystem --with-api

    # Validate an existing project
    skeleton dev validate ./my-project

===============================================================================
""".strip()


def run_dev_cli(argv: Optional[List[str]] = None) -> Any:
    """Main entry point for `skeleton dev` commands."""
    argv = argv or sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(dev_help_text())
        return {"status": "help_shown"}

    command = argv[0]
    args = argv[1:]

    if command == "list-templates":
        from skeleton.developer.scaffold import ScaffoldEngine
        engine = ScaffoldEngine(Path("."))
        templates = engine.list_templates()
        print("Available templates:")
        for t in templates:
            print(f"  * {t['name']:<20} — {t['description']}")
        return {"templates": templates}

    if command == "validate":
        if not args:
            print("Usage: skeleton dev validate <path>")
            return {"error": "missing_path"}
        path = Path(args[0])
        if not path.exists():
            print(f"Path not found: {path}")
            return {"error": "path_not_found"}
        from skeleton.developer.scaffold import ScaffoldEngine
        engine = ScaffoldEngine(path)
        results = engine.validate_project(path)
        print(json.dumps(results, indent=2))
        return results

    if command == "docs":
        topic = args[0] if args else "overview"
        return show_docs(topic)

    from skeleton.developer.commands import run_dev_command
    return run_dev_command(command, args)


def show_docs(topic: str) -> Dict[str, Any]:
    """Show documentation for a topic."""
    docs: Dict[str, str] = {
        "overview": """
Skeleton is a v16 AI game engine / agent orchestration framework.

Key concepts:
- Genesis — Boot protocol that wires all subsystems
- Forge — Blueprint-based system composition and Godot emit
- Swarm — Multi-agent mesh with negotiation and stigmergy
- Cortex — Observability and control surface
- Organism — Runtime health, config, and feature flags
        """.strip(),
        "genesis": """
Genesis Boot Protocol

Phases (in order):
1. kernel    — EventBus, EntropyPool, VectorClock, InvariantLattice
2. memory    — RAG, CAG, MAG, Trinity, DreamEngine, DriftDetector
3. intelligence — Orchestrator, AdaptiveLearner
4. swarm     — SwarmMesh, PheromoneField, HiveMind, Platoons
5. resilience — ResilienceFortress, CanaryRegistry
6. interface — AnomalyDetector, ProvenanceLedger, Reranker, QuadRetriever
7. cortex    — JeevesCortex (observes the whole bus)

Usage:
    from skeleton import Genesis
    genesis = Genesis(seed=42).boot()
    memory = genesis.get("rag")
        """.strip(),
        "forge": """
Universal Forge

The forge composes systems from blueprints:

    forge = Forge()
    bp = forge.new_blueprint("my_game")
    forge.instantiate(bp, "player", "hero")
    forge.instantiate(bp, "enemy_spawner", "spawner")
    bp.connect(("hero", "intent"), ("spawner", "tick"))
    result = forge.materialise(bp, era="extraction_now", target="godot")

Verification:
    Godot targets run through ForgeVerifier + optional repair loop.
        """.strip(),
        "swarm": """
Swarm Subsystem

Multi-agent coordination:
- SwarmMesh — Route tasks to capable agents
- PheromoneField — Stigmergic communication
- HiveMind — Collective reasoning
- CapabilityNegotiator — Dynamic capability discovery
- Platoons — Pre-configured agent groups

    mesh = SwarmMesh()
    agent = mesh.join({"reasoning", "vision"}, weight=2.0)
    assigned = mesh.route("reasoning")
        """.strip(),
        "api": """
REST API

FastAPI routes at skeleton.api.routes:
- /health, /health/live, /health/ready
- /genesis, /genesis/handles
- /retrieval/query, /retrieval/ingest, /retrieval/feedback
- /jeeves/session, /jeeves/interact, /jeeves/review
- /swarm/stats, /swarm/agent, /swarm/route
- /forge/blueprint, /forge/materialise, /forge/kinds, /forge/eras, /forge/archetype
- /pipeline/npc, /pipeline/game-logic, /pipeline/animation
- /gameforge/run, /gameforge/intake

Protected routes (HMAC seal):
    POST /forge/blueprint, /forge/materialise, /forge/archetype
    POST /gameforge/run, /gameforge/intake
        """.strip(),
        "testing": """
Testing Framework

skeleton.testing.scaffold provides:
- TestCase — Enhanced unittest.TestCase
- TestScaffold — Test environment setup
- TestOutcome — Structured test results

Run tests:
    python -m skeleton test
    pytest skeleton/testing/

Smoke tests:
    ./scripts/verify-forge.sh
    ./scripts/cockpit-smoke.sh
        """.strip(),
    }

    content = docs.get(topic, f"No documentation found for '{topic}'. Available: {', '.join(docs.keys())}")
    print(content)
    return {"topic": topic, "content": content}


def integrate_with_main() -> str:
    """Return the patch needed to add `dev` to skeleton.__main__.py."""
    return """
# Add to skeleton/__main__.py in the main command dispatcher:
#
#     elif cmd == "dev":
#         from skeleton.developer.cli import run_dev_cli
#         result = run_dev_cli(args)
#         if isinstance(result, dict):
#             print(json.dumps(result, indent=2, default=str))
#         sys.exit(0 if (isinstance(result, dict) and "error" not in result) else 1)
#
# Also add "dev" to the CLI help text under "Operator deck commands" or as a new section.
""".strip()


# Entry point for direct execution
if __name__ == "__main__":
    result = run_dev_cli()
    if isinstance(result, dict) and "error" in result:
        sys.exit(1)
    sys.exit(0)
