"""
Skeleton Developer CLI - Command Registry

Integrates scaffold, wizard, health, visualize, and extension commands
into a unified developer interface.
"""

import sys
import os
from typing import Optional, Dict, Any

from skeleton.developer.scaffold import ScaffoldEngine, list_templates
from skeleton.developer.wizard import Wizard, WizardMode


class CommandRegistry:
    """Central registry for all developer CLI commands."""

    def __init__(self):
        self._commands = {
            "scaffold": self._cmd_scaffold,
            "wizard": self._cmd_wizard,
            "health": self._cmd_health,
            "visualize": self._cmd_visualize,
            "extension": self._cmd_extension,
        }

    def execute(self, command: str, args) -> Optional[str]:
        """Execute a registered command with parsed arguments."""
        handler = self._commands.get(command)
        if not handler:
            return f"Unknown command: {command}"
        return handler(args)

    def _cmd_scaffold(self, args) -> str:
        """Handle scaffold command."""
        engine = ScaffoldEngine(output_dir=args.output)

        if not args.template:
            templates = list_templates()
            lines = ["Available templates:", ""]
            for name, info in templates.items():
                lines.append(f"  {name:20s} - {info['description']}")
            lines.append("")
            lines.append("Usage: skeleton dev scaffold <template> --name <project>")
            return "\n".join(lines)

        project_name = args.name or args.template
        result = engine.create_project(args.template, project_name, force=args.force)
        return result

    def _cmd_wizard(self, args) -> str:
        """Handle wizard command."""
        mode = WizardMode(args.mode) if args.mode else WizardMode.FULL
        wizard = Wizard(mode=mode)
        return wizard.run()

    def _cmd_health(self, args) -> str:
        """Handle health check command."""
        lines = ["Skeleton System Health", "=" * 40]
        
        # Check core modules
        core_modules = [
            "skeleton.genesis",
            "skeleton.forge.universal",
            "skeleton.intelligence.orchestrator",
            "skeleton.api.routes",
        ]
        
        for module in core_modules:
            try:
                __import__(module)
                status = "OK"
            except ImportError as e:
                status = f"MISSING ({e})"
            lines.append(f"  {module:30s} {status}")

        # Check developer modules
        dev_modules = [
            "skeleton.developer.scaffold",
            "skeleton.developer.wizard",
            "skeleton.developer.commands",
        ]
        
        lines.append("")
        lines.append("Developer CLI:")
        for module in dev_modules:
            try:
                __import__(module)
                status = "OK"
            except ImportError as e:
                status = f"MISSING ({e})"
            lines.append(f"  {module:30s} {status}")

        if args.verbose:
            lines.append("")
            lines.append("Environment:")
            lines.append(f"  Python: {sys.version}")
            lines.append(f"  Platform: {sys.platform}")
            lines.append(f"  Working dir: {os.getcwd()}")

        return "\n".join(lines)

    def _cmd_visualize(self, args) -> str:
        """Handle visualize command."""
        target = args.target or "skeleton.forge.universal"
        fmt = args.format

        try:
            module = __import__(target, fromlist=["Blueprint"])
            blueprint = getattr(module, "Blueprint", None)
        except ImportError:
            blueprint = None

        if not blueprint:
            return f"Could not load blueprint from {target}"

        if fmt == "text":
            lines = [f"Blueprint: {target}", "=" * 40]
            for attr in dir(blueprint):
                if not attr.startswith("_"):
                    val = getattr(blueprint, attr)
                    if callable(val):
                        lines.append(f"  [method] {attr}")
                    else:
                        lines.append(f"  [field]  {attr} = {val}")
            return "\n".join(lines)

        elif fmt == "json":
            import json
            schema = {"target": target, "methods": [], "fields": []}
            for attr in dir(blueprint):
                if not attr.startswith("_"):
                    val = getattr(blueprint, attr)
                    if callable(val):
                        schema["methods"].append(attr)
                    else:
                        schema["fields"].append({"name": attr, "value": str(val)})
            return json.dumps(schema, indent=2)

        else:
            return f"Format '{fmt}' visualization not yet implemented"

    def _cmd_extension(self, args) -> str:
        """Handle extension management command."""
        action = args.action
        name = args.name

        ext_dir = os.path.expanduser("~/.skeleton/extensions")
        os.makedirs(ext_dir, exist_ok=True)

        if action == "list":
            exts = os.listdir(ext_dir) if os.path.exists(ext_dir) else []
            if not exts:
                return "No extensions installed."
            lines = ["Installed extensions:", ""]
            for ext in exts:
                lines.append(f"  - {ext}")
            return "\n".join(lines)

        elif action == "install":
            if not name:
                return "Extension name required for install"
            ext_path = os.path.join(ext_dir, name)
            os.makedirs(ext_path, exist_ok=True)
            with open(os.path.join(ext_path, "__init__.py"), "w") as f:
                f.write(f'"""Extension: {name}"""\n')
            return f"Extension '{name}' installed to {ext_path}"

        elif action == "remove":
            if not name:
                return "Extension name required for remove"
            ext_path = os.path.join(ext_dir, name)
            if os.path.exists(ext_path):
                import shutil
                shutil.rmtree(ext_path)
                return f"Extension '{name}' removed"
            return f"Extension '{name}' not found"

        elif action == "update":
            return "Extension update not yet implemented"

        return f"Unknown extension action: {action}"
