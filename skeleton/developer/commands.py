"""
Skeleton Developer CLI — Command integration and extension generator

Provides:
- New CLI commands: dev scaffold, dev wizard, dev health, dev visualize
- Extension generator for new subsystems
- Developer utility commands
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton import Genesis
from skeleton.api.server import get_state
from skeleton.forge.universal import Forge


class DevCommandRegistry:
    """Registry for all developer CLI commands."""

    def __init__(self):
        self.commands: Dict[str, Any] = {}

    def register(self, name: str, handler: Any) -> None:
        self.commands[name] = handler

    def run(self, name: str, args: List[str]) -> Any:
        handler = self.commands.get(name)
        if handler is None:
            raise ValueError(f"Unknown dev command: {name}")
        return handler(args)


class ScaffoldCommand:
    """skeleton dev scaffold — Generate projects from templates."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev scaffold")
        parser.add_argument("project_name", help="Name of the new project")
        parser.add_argument("--template", "-t", default="minimal-agent",
                          choices=["minimal-agent", "game-forge", "swarm-orchestrator"],
                          help="Project template to use")
        parser.add_argument("--dir", "-d", default=".", help="Target directory")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
        parsed = parser.parse_args(args)

        from skeleton.developer.scaffold import ScaffoldEngine

        engine = ScaffoldEngine(Path(parsed.dir))
        templates = engine.list_templates()

        if parsed.dry_run:
            return {
                "action": "dry_run",
                "project_name": parsed.project_name,
                "template": parsed.template,
                "target_dir": str(Path(parsed.dir) / parsed.project_name),
                "available_templates": templates,
            }

        dest = engine.scaffold(parsed.template, parsed.project_name)
        validation = engine.validate_project(dest)

        return {
            "action": "scaffold",
            "project_name": parsed.project_name,
            "template": parsed.template,
            "created_at": str(dest),
            "validation": validation,
            "next_steps": [
                f"cd {dest}",
                "Edit config/settings.yaml",
                "Run: skeleton dev health",
            ],
        }


class WizardCommand:
    """skeleton dev wizard — Interactive project creation."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        from skeleton.developer.wizard import ProjectWizard, ScaffoldEngine

        engine = ScaffoldEngine(Path("."))
        wizard = ProjectWizard(engine)

        # Check for --non-interactive with --answers
        parser = argparse.ArgumentParser(prog="skeleton dev wizard")
        parser.add_argument("--answers", type=str, help="JSON string of pre-filled answers")
        parser.add_argument("--non-interactive", action="store_true", help="Use default answers")
        parsed = parser.parse_args(args)

        answers = None
        if parsed.answers:
            answers = json.loads(parsed.answers)
        elif parsed.non_interactive:
            answers = {
                "project_type": "minimal-agent",
                "project_name": "my-skeleton-project",
                "subsystem_bundle": "all",
                "target_platform": "json",
            }

        plan = wizard.run(answers)

        if not parsed.non_interactive and not parsed.answers:
            # In interactive mode, offer to scaffold immediately
            print("\nProject plan generated:")
            print(json.dumps(plan, indent=2))
            try:
                proceed = input("\nScaffold now? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                proceed = "n"

            if proceed in ("", "y", "yes"):
                scaffold = ScaffoldCommand()
                return scaffold([
                    plan["project_name"],
                    "--template", plan["template"],
                ])

        return plan


class HealthCommand:
    """skeleton dev health — Subsystem health dashboard."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev health")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
        parser.add_argument("--interval", type=int, default=5, help="Watch interval in seconds")
        parsed = parser.parse_args(args)

        from skeleton.developer.wizard import SubsystemExplorer

        try:
            state = get_state()
        except Exception:
            # Fallback: boot a fresh genesis for standalone health check
            genesis = Genesis(seed=42).boot()
            state = type("MockState", (), {"genesis": genesis})()

        explorer = SubsystemExplorer(state)

        if parsed.watch:
            import time
            try:
                while True:
                    summary = explorer.summary()
                    self._render_summary(summary, parsed.json)
                    time.sleep(parsed.interval)
            except KeyboardInterrupt:
                print("\nHealth watch stopped.")
                return {"status": "stopped"}

        summary = explorer.summary()
        self._render_summary(summary, parsed.json)
        return summary

    @staticmethod
    def _render_summary(summary: Dict[str, Any], as_json: bool) -> None:
        if as_json:
            print(json.dumps(summary, indent=2, default=str))
            return

        from skeleton.developer.wizard import SubsystemExplorer
        explorer = SubsystemExplorer()
        print(explorer.render_table())
        print(f"\nOverall: {summary['overall'].upper()}")
        print(f"Subsystems: {summary['total_subsystems']} | Phases: {summary['phases_booted']}")
        for status, count in summary.get("status_breakdown", {}).items():
            print(f"  {status}: {count}")


class VisualizeCommand:
    """skeleton dev visualize — Blueprint and topology visualization."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev visualize")
        parser.add_argument("--blueprint", "-b", help="Blueprint ID or name to visualize")
        parser.add_argument("--topology", "-t", action="store_true", help="Show topology as JSON")
        parser.add_argument("--compact", "-c", action="store_true", help="Compact output")
        parser.add_argument("--save", "-s", help="Save output to file")
        parsed = parser.parse_args(args)

        from skeleton.developer.wizard import BlueprintVisualizer

        if parsed.blueprint:
            # Try to find blueprint in running state
            try:
                state = get_state()
                forge = getattr(state, "forge", None)
                if forge is None:
                    raise RuntimeError("No forge available")
                # Blueprints aren't directly stored; create a sample for demo
                bp = forge.new_blueprint(parsed.blueprint)
                forge.instantiate(bp, "source", "input")
                forge.instantiate(bp, "transform", "process")
                forge.instantiate(bp, "sink", "output")
                bp.connect(("input", "out"), ("process", "in"))
                bp.connect(("process", "out"), ("output", "in"))
            except Exception:
                # Fallback: create a demo blueprint
                forge = Forge()
                bp = forge.new_blueprint(parsed.blueprint or "demo")
                forge.instantiate(bp, "source", "input")
                forge.instantiate(bp, "transform", "process")
                forge.instantiate(bp, "sink", "output")
                bp.connect(("input", "out"), ("process", "in"))
                bp.connect(("process", "out"), ("output", "in"))

            visualizer = BlueprintVisualizer()

            if parsed.topology:
                output = visualizer.render_topology(bp)
            else:
                output = visualizer.render(bp, compact=parsed.compact)

            if parsed.save:
                Path(parsed.save).write_text(output)
                return {"saved_to": parsed.save, "blueprint": bp.name}

            print(output)
            return {"blueprint": bp.name, "components": len(bp.components), "wires": len(bp.wires)}

        return {"error": "No blueprint specified. Use --blueprint <name>"}


class ExtensionCommand:
    """skeleton dev extension — Generate boilerplate for new subsystems."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev extension")
        parser.add_argument("name", help="Extension/subsystem name")
        parser.add_argument("--type", choices=["subsystem", "pipeline", "agent", "tool"], default="subsystem")
        parser.add_argument("--with-tests", action="store_true", default=True, help="Generate tests")
        parser.add_argument("--with-api", action="store_true", help="Generate API routes")
        parsed = parser.parse_args(args)

        dest = Path("extensions") / parsed.name
        dest.mkdir(parents=True, exist_ok=True)

        files = self._generate_files(parsed.name, parsed.type, parsed.with_tests, parsed.with_api)
        for path, content in files.items():
            file_path = dest / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content.strip() + "\n")

        return {
            "extension": parsed.name,
            "type": parsed.type,
            "created_at": str(dest),
            "files": list(files.keys()),
        }

    @staticmethod
    def _generate_files(name: str, ext_type: str, with_tests: bool, with_api: bool) -> Dict[str, str]:
        files: Dict[str, str] = {}

        class_name = "".join(p.capitalize() for p in name.split("_"))

        if ext_type == "subsystem":
            files[f"{name}/__init__.py"] = f'''"""{class_name} subsystem for Skeleton."""
from skeleton.kernel.events import EventBus

class {class_name}:
    def __init__(self, bus: EventBus | None = None):
        self.bus = bus or EventBus()
        self._state = {{}}

    def health(self) -> dict:
        return {{"healthy": True, "state": self._state}}

    def stats(self) -> dict:
        return {{"events_processed": 0}}
'''

        elif ext_type == "pipeline":
            files[f"{name}/__init__.py"] = f'''"""{class_name} pipeline for Skeleton."""
from skeleton.kernel.events import EventBus

class {class_name}Pipeline:
    def __init__(self, bus: EventBus | None = None):
        self.bus = bus or EventBus()

    def run(self, description: str, **kwargs) -> dict:
        """Execute the pipeline."""
        return {{
            "description": description,
            "status": "generated",
            "result": {{}},
        }}
'''

        elif ext_type == "agent":
            files[f"{name}/__init__.py"] = f'''"""{class_name} agent for Skeleton."""
from skeleton import Genesis

class {class_name}Agent:
    def __init__(self):
        self.genesis = Genesis(seed=42).boot()

    def act(self, observation: str) -> str:
        """Process observation and return action."""
        return f"Action for: {{observation}}"
'''

        elif ext_type == "tool":
            files[f"{name}/__init__.py"] = f'''"""{class_name} tool for Skeleton."""
class {class_name}Tool:
    def __init__(self):
        pass

    def invoke(self, **params) -> dict:
        """Invoke the tool with parameters."""
        return {{"result": None, "params": params}}
'''

        if with_tests:
            files[f"tests/test_{name}.py"] = f'''"""Tests for {name}."""
from skeleton.testing.scaffold import TestCase

class Test{class_name}(TestCase):
    def test_initialization(self):
        # TODO: Import and test your extension
        pass
'''

        if with_api:
            files[f"{name}/routes.py"] = f'''"""API routes for {name}."""
from fastapi import APIRouter

router = APIRouter(prefix="/{name}")

@router.get("/health")
async def health() -> dict:
    return {{"status": "healthy"}}
'''

        return files


# Global registry instance
_dev_registry = DevCommandRegistry()
_dev_registry.register("scaffold", ScaffoldCommand())
_dev_registry.register("wizard", WizardCommand())
_dev_registry.register("health", HealthCommand())
_dev_registry.register("visualize", VisualizeCommand())
_dev_registry.register("extension", ExtensionCommand())


def run_dev_command(command: str, args: List[str]) -> Any:
    """Entry point for all dev subcommands."""
    return _dev_registry.run(command, args)
