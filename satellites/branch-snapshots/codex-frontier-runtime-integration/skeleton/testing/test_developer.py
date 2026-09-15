"""Tests for the Skeleton Developer CLI.

Covers scaffold, wizard, commands, and cli modules.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from skeleton.testing.scaffold import TestCase


class TestScaffoldEngine(TestCase):
    def setUp(self):
        from skeleton.developer.scaffold import ScaffoldEngine
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = ScaffoldEngine(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_templates_returns_three(self):
        templates = self.engine.list_templates()
        self.assertEqual(len(templates), 3)
        names = {t["name"] for t in templates}
        self.assertEqual(names, {"minimal-agent", "game-forge", "swarm-orchestrator"})

    def test_scaffold_minimal_agent(self):
        dest = self.engine.scaffold("minimal-agent", "test-agent")
        self.assertTrue(dest.exists())
        self.assertTrue((dest / "src" / "agent.py").exists())
        self.assertTrue((dest / "tests" / "test_agent.py").exists())
        self.assertTrue((dest / "config" / "settings.yaml").exists())
        self.assertTrue((dest / "README.md").exists())

    def test_scaffold_game_forge(self):
        dest = self.engine.scaffold("game-forge", "test-game")
        self.assertTrue((dest / "src" / "game.py").exists())
        self.assertTrue((dest / "scripts" / "build.sh").exists())

    def test_scaffold_swarm(self):
        dest = self.engine.scaffold("swarm-orchestrator", "test-swarm")
        self.assertTrue((dest / "src" / "coordination" / "hive.py").exists())

    def test_scaffold_duplicate_raises(self):
        self.engine.scaffold("minimal-agent", "dup")
        with self.assertRaises(FileExistsError):
            self.engine.scaffold("minimal-agent", "dup")

    def test_validate_project(self):
        dest = self.engine.scaffold("minimal-agent", "val")
        results = self.engine.validate_project(dest)
        self.assertTrue(results["has_src"])
        self.assertTrue(results["has_tests"])
        self.assertTrue(results["has_config"])
        self.assertTrue(results["has_readme"])
        self.assertGreater(len(results["skeleton_imports"]), 0)


class TestProjectWizard(TestCase):
    def test_run_with_prefilled_answers(self):
        from skeleton.developer.scaffold import ScaffoldEngine
        from skeleton.developer.wizard import ProjectWizard

        engine = ScaffoldEngine(Path("."))
        wizard = ProjectWizard(engine)
        plan = wizard.run({
            "project_type": "game-forge",
            "project_name": "my-game",
            "subsystem_bundle": "all",
            "target_platform": "godot",
        })
        self.assertEqual(plan["project_name"], "my-game")
        self.assertEqual(plan["template"], "game-forge")
        self.assertEqual(plan["target"], "godot")
        self.assertIn("memory", plan["subsystems"])

    def test_parse_subsystems_all(self):
        from skeleton.developer.wizard import ProjectWizard
        result = ProjectWizard._parse_subsystems("all")
        self.assertEqual(len(result), 6)

    def test_parse_subsystems_partial(self):
        from skeleton.developer.wizard import ProjectWizard
        result = ProjectWizard._parse_subsystems("memory, swarm")
        self.assertEqual(result, ["memory", "swarm"])


class TestSubsystemExplorer(TestCase):
    def test_discover_with_mock_state(self):
        from skeleton.developer.wizard import SubsystemExplorer
        from skeleton import Genesis

        genesis = Genesis(seed=42).boot()
        mock_state = type("MockState", (), {"genesis": genesis})()
        explorer = SubsystemExplorer(mock_state)
        cards = explorer.discover()
        self.assertGreater(len(cards), 0)
        phases = {c.phase for c in cards}
        self.assertIn("kernel", phases)

    def test_summary_healthy(self):
        from skeleton.developer.wizard import SubsystemExplorer
        from skeleton import Genesis

        genesis = Genesis(seed=42).boot()
        mock_state = type("MockState", (), {"genesis": genesis})()
        explorer = SubsystemExplorer(mock_state)
        summary = explorer.summary()
        self.assertIn("overall", summary)
        self.assertIn("total_subsystems", summary)
        self.assertGreater(summary["total_subsystems"], 0)

    def test_render_table(self):
        from skeleton.developer.wizard import SubsystemExplorer
        from skeleton import Genesis

        genesis = Genesis(seed=42).boot()
        mock_state = type("MockState", (), {"genesis": genesis})()
        explorer = SubsystemExplorer(mock_state)
        table = explorer.render_table()
        self.assertIn("Subsystem", table)
        self.assertIn("kernel", table)


class TestBlueprintVisualizer(TestCase):
    def test_render_blueprint(self):
        from skeleton.developer.wizard import BlueprintVisualizer
        from skeleton.forge.universal import Forge

        forge = Forge()
        bp = forge.new_blueprint("test")
        forge.instantiate(bp, "source", "input")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("input", "out"), ("output", "in"))

        viz = BlueprintVisualizer()
        text = viz.render(bp)
        self.assertIn("test", text)
        self.assertIn("input", text)
        self.assertIn("output", text)

    def test_render_topology(self):
        from skeleton.developer.wizard import BlueprintVisualizer
        from skeleton.forge.universal import Forge

        forge = Forge()
        bp = forge.new_blueprint("test")
        forge.instantiate(bp, "source", "input")

        viz = BlueprintVisualizer()
        topo = viz.render_topology(bp)
        self.assertIn("blueprint_id", topo)
        self.assertIn("components", topo)


class TestDevCommands(TestCase):
    def test_scaffold_command_dry_run(self):
        from skeleton.developer.commands import ScaffoldCommand
        cmd = ScaffoldCommand()
        result = cmd(["test-proj", "--template", "minimal-agent", "--dry-run"])
        self.assertEqual(result["action"], "dry_run")
        self.assertEqual(result["template"], "minimal-agent")

    def test_health_command_json(self):
        from skeleton.developer.commands import HealthCommand
        cmd = HealthCommand()
        result = cmd(["--json"])
        self.assertIn("overall", result)
        self.assertIn("status_breakdown", result)

    def test_extension_command(self):
        from skeleton.developer.commands import ExtensionCommand
        import tempfile, shutil

        tmp = Path(tempfile.mkdtemp())
        orig = Path.cwd()
        try:
            import os
            os.chdir(tmp)
            cmd = ExtensionCommand()
            result = cmd(["my_ext", "--type", "subsystem"])
            self.assertEqual(result["extension"], "my_ext")
            self.assertTrue((tmp / "extensions" / "my_ext" / "my_ext" / "__init__.py").exists())
        finally:
            os.chdir(orig)
            shutil.rmtree(tmp, ignore_errors=True)


class TestDevCliEntry(TestCase):
    def test_help_shown(self):
        from skeleton.developer.cli import run_dev_cli
        result = run_dev_cli(["help"])
        self.assertEqual(result["status"], "help_shown")

    def test_list_templates(self):
        from skeleton.developer.cli import run_dev_cli
        result = run_dev_cli(["list-templates"])
        self.assertIn("templates", result)
        self.assertEqual(len(result["templates"]), 3)

    def test_docs_overview(self):
        from skeleton.developer.cli import show_docs
        result = show_docs("overview")
        self.assertIn("Genesis", result["content"])

    def test_docs_unknown_topic(self):
        from skeleton.developer.cli import show_docs
        result = show_docs("nonexistent")
        self.assertIn("No documentation found", result["content"])
