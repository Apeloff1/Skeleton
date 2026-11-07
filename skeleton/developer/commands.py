"""
Skeleton Developer CLI — Command integration and extension generator

Provides:
- New CLI commands: dev scaffold, dev wizard, dev health, dev visualize
- Extension generator for new subsystems
- Persistence commands: dev snapshot, dev restore, dev snapshots
- Developer utility commands
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from skeleton.forge.universal import Forge


_EXTENSION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


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


# Historical import compatibility. Keep the module-level name used by older
# callers while retaining DevCommandRegistry as the canonical class name.
CommandRegistry = DevCommandRegistry


class ScaffoldCommand:
    """skeleton dev scaffold — Generate projects from templates."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        from skeleton.developer.scaffold import ScaffoldEngine, TEMPLATES

        parser = argparse.ArgumentParser(prog="skeleton dev scaffold")
        parser.add_argument("project_name", help="Name of the new project")
        parser.add_argument("--template", "-t", default="minimal-agent", choices=sorted(TEMPLATES), help="Project template to use")
        parser.add_argument("--dir", "-d", default=".", help="Target directory")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
        parsed = parser.parse_args(args)

        engine = ScaffoldEngine(Path(parsed.dir))
        templates = engine.list_templates()
        if parsed.dry_run:
            try:
                target = engine._project_dir(parsed.project_name)
            except ValueError as exc:
                return {"action": "dry_run", "error": str(exc)}
            return {"action": "dry_run", "project_name": parsed.project_name, "template": parsed.template, "target_dir": str(target), "available_templates": templates}

        try:
            dest = engine.scaffold(parsed.template, parsed.project_name)
        except (FileExistsError, ValueError) as exc:
            return {"action": "scaffold", "project_name": parsed.project_name, "template": parsed.template, "error": str(exc)}
        validation = engine.validate_project(dest)
        return {"action": "scaffold", "project_name": parsed.project_name, "template": parsed.template, "created_at": str(dest), "validation": validation, "next_steps": [f"cd {dest}", "Edit config/settings.yaml", "Run: skeleton dev health"]}


class WizardCommand:
    """skeleton dev wizard — Interactive project creation."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        from skeleton.developer.scaffold import ScaffoldEngine
        from skeleton.developer.wizard import ProjectWizard
        engine = ScaffoldEngine(Path("."))
        wizard = ProjectWizard(engine)
        parser = argparse.ArgumentParser(prog="skeleton dev wizard")
        parser.add_argument("--answers", type=str, help="JSON string of pre-filled answers")
        parser.add_argument("--non-interactive", action="store_true", help="Use default answers")
        parsed = parser.parse_args(args)
        answers = None
        if parsed.answers:
            answers = json.loads(parsed.answers)
        elif parsed.non_interactive:
            answers = {"project_type": "minimal-agent", "project_name": "my-skeleton-project", "subsystem_bundle": "all", "target_platform": "json"}
        plan = wizard.run(answers)
        if not parsed.non_interactive and not parsed.answers:
            print("\nProject plan generated:")
            print(json.dumps(plan, indent=2))
            try:
                proceed = input("\nScaffold now? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                proceed = "n"
            if proceed in ("", "y", "yes"):
                return ScaffoldCommand()([plan["project_name"], "--template", plan["template"]])
        return plan


class HealthCommand:
    """skeleton dev health — Subsystem health dashboard (+ STU-TOOLS deepen/gates)."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev health")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
        parser.add_argument("--interval", type=int, default=5, help="Watch interval in seconds")
        parser.add_argument("--deepen", action="store_true", help="STU-TOOLS deepened health report")
        parser.add_argument("--gates", action="store_true", help="STU-TOOLS fail-closed health gates")
        parsed = parser.parse_args(args)
        from skeleton.developer.wizard import SubsystemExplorer
        explorer = SubsystemExplorer()
        if parsed.gates or parsed.deepen:
            from skeleton.developer.health_gates import run_health_gates
            from skeleton.developer.health_deepen import deepen_health_report, render_health_deep
            if parsed.gates:
                result = run_health_gates(explorer=explorer)
            else:
                result = deepen_health_report(explorer=explorer)
            if parsed.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                if parsed.gates:
                    from skeleton.developer.gate_verdict import gate_table
                    verdict = result.get("verdict") or {}
                    # gate_table needs Verdict — print banner + JSON subset
                    print(result.get("banner") or verdict.get("banner") or "")
                    print(json.dumps({"ok": result.get("ok"), "blocking": verdict.get("blocking")}, indent=2))
                else:
                    try:
                        print(render_health_deep(result))
                    except Exception:
                        print(json.dumps(result, indent=2, default=str))
            return result
        if parsed.watch:
            import time
            try:
                while True:
                    summary = explorer.summary()
                    self._render_summary(summary, parsed.json, explorer)
                    time.sleep(parsed.interval)
            except KeyboardInterrupt:
                print("\nHealth watch stopped.")
                return {"status": "stopped"}
        summary = explorer.summary()
        self._render_summary(summary, parsed.json, explorer)
        return summary

    @staticmethod
    def _render_summary(summary: Dict[str, Any], as_json: bool, explorer: Any) -> None:
        if as_json:
            print(json.dumps(summary, indent=2, default=str))
            return
        print(explorer.render_table())
        print(f"\nOverall: {summary['overall'].upper()}")
        print(f"Subsystems: {summary['total_subsystems']} | Phases: {summary['phases_booted']}")
        for status, count in summary.get("status_breakdown", {}).items():
            print(f"  {status}: {count}")


class VisualizeCommand:
    """skeleton dev visualize — Blueprint and topology visualization (+ STU-TOOLS deepen/gates)."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev visualize")
        parser.add_argument("--blueprint", "-b", help="Blueprint ID or name to visualize")
        parser.add_argument("--topology", "-t", action="store_true", help="Show topology as JSON")
        parser.add_argument("--compact", "-c", action="store_true", help="Compact output")
        parser.add_argument("--save", "-s", help="Save output to file")
        parser.add_argument("--deepen", action="store_true", help="STU-TOOLS deepened visualize report")
        parser.add_argument("--gates", action="store_true", help="STU-TOOLS fail-closed visualize gates")
        parsed = parser.parse_args(args)
        from skeleton.developer.wizard import BlueprintVisualizer
        if parsed.blueprint:
            forge = Forge()
            bp = forge.new_blueprint(parsed.blueprint)
            forge.instantiate(bp, "source", "input")
            forge.instantiate(bp, "transform", "process")
            forge.instantiate(bp, "sink", "output")
            bp.connect(("input", "out"), ("process", "in"))
            bp.connect(("process", "out"), ("output", "in"))
            if parsed.gates or parsed.deepen:
                from skeleton.developer.visualize_gates import run_visualize_gates
                from skeleton.developer.visualize_deepen import deepen_visualize_report, render_visualize_deep
                result = run_visualize_gates(bp) if parsed.gates else deepen_visualize_report(bp, compact=parsed.compact)
                if parsed.json if hasattr(parsed, "json") else False:
                    print(json.dumps(result, indent=2, default=str))
                elif parsed.gates:
                    print(result.get("banner") or "")
                    print(json.dumps({"ok": result.get("ok"), "blocking": (result.get("verdict") or {}).get("blocking")}, indent=2))
                else:
                    try:
                        print(render_visualize_deep(result))
                    except Exception:
                        print(json.dumps(result, indent=2, default=str))
                if parsed.save:
                    Path(parsed.save).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
                    result = dict(result)
                    result["saved_to"] = parsed.save
                return result
            visualizer = BlueprintVisualizer()
            output = visualizer.render_topology(bp) if parsed.topology else visualizer.render(bp, compact=parsed.compact)
            if parsed.save:
                Path(parsed.save).write_text(str(output), encoding="utf-8")
                return {"saved_to": parsed.save, "blueprint": bp.name}
            print(output)
            return {"blueprint": bp.name, "components": len(bp.components), "wires": len(bp.wires)}
        return {"error": "No blueprint specified. Use --blueprint <name>"}



class DoctorCommand:
    """skeleton dev doctor — STU-TOOLS doctor/cockpit deepen + fail-closed gates."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev doctor")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--gates", action="store_true", help="Run fail-closed doctor gates")
        parser.add_argument("--card", type=str, help="Path to doctor card JSON")
        parsed = parser.parse_args(args)
        card = None
        if parsed.card:
            card = json.loads(Path(parsed.card).read_text(encoding="utf-8"))
        if parsed.gates:
            from skeleton.developer.doctor_gates import run_doctor_gates
            result = run_doctor_gates(card=card)
        else:
            from skeleton.developer.doctor_deepen import deepen_doctor_report, render_doctor_deep
            result = deepen_doctor_report(card=card)
        if parsed.json or parsed.gates:
            if parsed.gates and not parsed.json:
                print(result.get("banner") or "")
            print(json.dumps(result if parsed.json else {"ok": result.get("ok"), "banner": result.get("banner")}, indent=2, default=str) if parsed.gates and not parsed.json else json.dumps(result, indent=2, default=str))
        else:
            from skeleton.developer.doctor_deepen import render_doctor_deep
            print(render_doctor_deep(result))
        return result


class RegenCommand:
    """skeleton dev regen — STU-TOOLS weakest-surface regenerate plan/apply."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev regen")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--apply", action="store_true", help="Apply regenerations (default dry-run)")
        parser.add_argument("--artefacts", type=str, help="JSON object of path->content")
        parser.add_argument("--allow-empty", action="store_true", help="Allow empty regen plans")
        parsed = parser.parse_args(args)
        artefacts = {"stubs/ok.gd": "extends Node\nfunc _ready() -> void:\n    pass\n"}
        if parsed.artefacts:
            artefacts = json.loads(Path(parsed.artefacts).read_text(encoding="utf-8"))
        from skeleton.developer.weakest_regenerate import run_weakest_regenerate
        result = run_weakest_regenerate(
            artefacts=artefacts,
            dry_run=not parsed.apply,
            allow_empty=parsed.allow_empty,
        )
        print(json.dumps(result, indent=2, default=str))
        return result


class StuToolsCommand:
    """skeleton dev stu-tools — full STU-TOOLS pipeline (health/visualize/doctor/regen)."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev stu-tools")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--paths", type=str, default="health,visualize,doctor,regen", help="Comma paths")
        parser.add_argument("--apply-regen", action="store_true", help="Apply regen (default dry-run)")
        parser.add_argument("--ci-bundle", action="store_true", help="CI bundle with cockpit+bridge+coverage")
        parsed = parser.parse_args(args)
        if parsed.ci_bundle:
            from skeleton.developer.stu_tools_report import run_stu_tools_ci_bundle
            result = run_stu_tools_ci_bundle(
                paths=[p.strip() for p in parsed.paths.split(",") if p.strip()],
            )
        else:
            from skeleton.developer.stu_tools_pipeline import run_stu_tools_pipeline
            result = run_stu_tools_pipeline(
                paths=[p.strip() for p in parsed.paths.split(",") if p.strip()],
                dry_run_regen=not parsed.apply_regen,
            )
        if parsed.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(result.get("gate_table") or result.get("banner") or "")
            print(json.dumps({"ok": result.get("ok"), "banner": result.get("banner"), "paths": result.get("paths")}, indent=2))
        return result



class CockpitCommand:
    """skeleton dev cockpit — STU-TOOLS cockpit deepen + fail-closed gates."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev cockpit")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--gates", action="store_true", help="Run fail-closed cockpit gates")
        parser.add_argument("--retune", action="store_true", help="Auto-retune out-of-range knobs")
        parser.add_argument("--knobs", type=str, help="JSON object of knob values")
        parsed = parser.parse_args(args)
        knobs = json.loads(parsed.knobs) if parsed.knobs else None
        if parsed.gates or parsed.retune:
            from skeleton.developer.cockpit_gates import run_cockpit_gates
            result = run_cockpit_gates(knobs, auto_retune=parsed.retune)
        else:
            from skeleton.developer.cockpit_deepen import deepen_cockpit_report, render_cockpit_deep
            result = deepen_cockpit_report(knobs)
        if parsed.json or parsed.gates or parsed.retune:
            print(json.dumps(result, indent=2, default=str))
        else:
            from skeleton.developer.cockpit_deepen import render_cockpit_deep
            print(render_cockpit_deep(result))
        return result


class BridgeCommand:
    """skeleton dev bridge — doctor↔cockpit bridge plan/gates."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev bridge")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--apply", action="store_true", help="Apply proposed clamps")
        parser.add_argument("--card", type=str, help="Doctor card JSON path")
        parsed = parser.parse_args(args)
        card = json.loads(Path(parsed.card).read_text(encoding="utf-8")) if parsed.card else None
        from skeleton.developer.doctor_cockpit_bridge import run_doctor_cockpit_bridge
        result = run_doctor_cockpit_bridge(doctor_card=card, apply=parsed.apply)
        print(json.dumps(result, indent=2, default=str))
        return result


class ExtensionCommand:
    """skeleton dev extension — Generate boilerplate for new subsystems."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev extension")
        parser.add_argument("name", help="Extension/subsystem name")
        parser.add_argument("--type", choices=["subsystem", "pipeline", "agent", "tool"], default="subsystem")
        parser.add_argument("--with-tests", action=argparse.BooleanOptionalAction, default=True, help="Generate tests")
        parser.add_argument("--with-api", action="store_true", help="Generate API routes")
        parsed = parser.parse_args(args)
        if not _EXTENSION_NAME.fullmatch(parsed.name):
            return {"extension": parsed.name, "error": "extension name must start with a letter and contain only letters, numbers, and underscores"}
        dest = Path("extensions") / parsed.name
        dest.mkdir(parents=True, exist_ok=True)
        files = self._generate_files(parsed.name, parsed.type, parsed.with_tests, parsed.with_api)
        for path, content in files.items():
            file_path = dest / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content.strip() + "\n", encoding="utf-8")
        return {"extension": parsed.name, "type": parsed.type, "created_at": str(dest), "files": list(files.keys())}

    @staticmethod
    def _generate_files(name: str, ext_type: str, with_tests: bool, with_api: bool) -> Dict[str, str]:
        files: Dict[str, str] = {}
        class_name = "".join(part.capitalize() for part in name.split("_"))
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
        return {{"description": description, "status": "generated", "result": {{}}}}
'''
        elif ext_type == "agent":
            files[f"{name}/__init__.py"] = f'''"""{class_name} agent for Skeleton."""
from skeleton import Genesis

class {class_name}Agent:
    def __init__(self):
        self.genesis = Genesis(seed=42).boot()
    def act(self, observation: str) -> str:
        return f"Action for: {{observation}}"
'''
        elif ext_type == "tool":
            files[f"{name}/__init__.py"] = f'''"""{class_name} tool for Skeleton."""
class {class_name}Tool:
    def invoke(self, **params) -> dict:
        return {{"result": None, "params": params}}
'''
        if with_tests:
            files[f"tests/test_{name}.py"] = f'''"""Tests for {name}."""
from skeleton.testing.scaffold import TestCase

class Test{class_name}(TestCase):
    def test_initialization(self):
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


from skeleton.developer.persistence_commands import RestoreCommand, SnapshotCommand, SnapshotsCommand

_dev_registry = DevCommandRegistry()
_dev_registry.register("scaffold", ScaffoldCommand())
_dev_registry.register("wizard", WizardCommand())
_dev_registry.register("health", HealthCommand())
_dev_registry.register("visualize", VisualizeCommand())
_dev_registry.register("doctor", DoctorCommand())
_dev_registry.register("cockpit", CockpitCommand())
_dev_registry.register("bridge", BridgeCommand())
_dev_registry.register("regen", RegenCommand())
_dev_registry.register("stu-tools", StuToolsCommand())
_dev_registry.register("extension", ExtensionCommand())
_dev_registry.register("snapshot", SnapshotCommand())
_dev_registry.register("restore", RestoreCommand())
_dev_registry.register("snapshots", SnapshotsCommand())


def run_dev_command(command: str, args: List[str]) -> Any:
    """Entry point for all dev subcommands."""
    return _dev_registry.run(command, args)
