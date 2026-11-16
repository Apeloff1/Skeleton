"""Evidence-bound static graph, cycle ordering and nonexecution regressions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.app.orphan_source_graph import GraphBudget, GraphError, analyze
from skeleton.app.orphan_source_graph_cli import main


def write(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


@pytest.fixture
def source(tmp_path):
    for path, content in {
        "pyproject.toml": '[project.scripts]\nskeleton = "skeleton.__main__:main"\n',
        "setup.cfg": "[options.entry_points]\nconsole_scripts =\n  skeleton = skeleton.__main__:main\n",
        "skeleton/__init__.py": "",
        "skeleton/__main__.py": "from skeleton.live import main\n",
        "skeleton/live.py": "from skeleton import shared\ndef main(argv=None): pass\n",
        "skeleton/shared.py": "",
        "skeleton/hidden/__init__.py": "",
        "skeleton/hidden/outer.py": "from . import cycle_a\n",
        "skeleton/hidden/cycle_a.py": "from . import cycle_b\n",
        "skeleton/hidden/cycle_b.py": "from . import cycle_a\nfrom skeleton import leaf\n",
        "skeleton/leaf.py": "raise RuntimeError('never execute this file')\n",
        "skeleton/hidden/dynamic.py": "import importlib as loader\nloader.import_module('skeleton.leaf')\nloader.import_module(variable)\n",
        "skeleton/tests/test_only.py": "from skeleton import leaf\n",
    }.items():
        write(tmp_path, path, content)
    return tmp_path


def by_module(report):
    return {module: component for component in report["components"]
            for module in component["modules"]}


def test_cycle_and_dependency_order(source):
    report = analyze(source)
    assert report["source_inventory_complete"]
    assert report["statically_referenced_modules"] == 4
    components = by_module(report)
    assert "skeleton.live" not in components
    assert "skeleton.tests.test_only" not in components
    cycle = components["skeleton.hidden.cycle_a"]
    assert cycle == components["skeleton.hidden.cycle_b"]
    assert components["skeleton.leaf"]["dependency_wave"] < cycle["dependency_wave"]
    assert cycle["dependency_wave"] < components["skeleton.hidden.outer"]["dependency_wave"]
    assert report["dynamic_unknown_calls"] == 1
    assert report["runtime_reachability_verified"] is False
    assert report["automatic_activation_authorized"] is False
    assert analyze(source) == report


def test_explicit_root_reclassifies_transitive_dependencies(source):
    report = analyze(source, extra_roots=["skeleton.hidden.outer"])
    for name in ("skeleton.hidden.outer", "skeleton.hidden.cycle_a",
                 "skeleton.hidden.cycle_b", "skeleton.leaf"):
        assert name not in by_module(report)
    assert "skeleton.hidden.dynamic" in by_module(report)


def test_changes_bind_source_and_plan_digests(source):
    before = analyze(source)
    write(source, "skeleton/leaf.py", "changed = True\n")
    after = analyze(source)
    assert before["source_inventory_digest"] != after["source_inventory_digest"]
    assert before["candidate_plan_digest"] != after["candidate_plan_digest"]
    assert before["graph_digest"] == after["graph_digest"]


def test_module_and_package_collision_is_not_certified(source):
    write(source, "skeleton/hidden.py", "flag = True\n")
    report = analyze(source)
    assert not report["source_inventory_complete"]
    assert any(x["reason"] == "ambiguous_module_identity"
               for x in report["scan"]["issues"])


def test_missing_root_and_metadata_drift_are_exposed(source):
    with (source / "pyproject.toml").open("a", encoding="utf-8") as out:
        out.write('missing = "skeleton.missing:main"\n')
    report = analyze(source)
    assert not report["source_inventory_complete"]
    assert "skeleton.missing" in report["missing_roots"]
    assert report["scan"]["metadata_drift"] == ["missing"]


def test_bounded_partial_scan_is_not_complete(source):
    report = analyze(source, budget=GraphBudget(entries=2))
    assert not report["source_inventory_complete"]
    assert report["scan"]["limit_reason"] == "entries"
    assert report["runtime_reachability_verified"] is False


def test_symbolic_link_omission_is_visible(source):
    try:
        (source / "skeleton" / "link.py").symlink_to(source / "skeleton" / "leaf.py")
    except OSError:
        pytest.skip("symlink unavailable")
    report = analyze(source)
    assert not report["source_inventory_complete"]
    assert report["scan"]["skipped_symlinks"] == 1


def test_edge_ceiling_is_hard_rejection(source):
    with pytest.raises(GraphError, match="edge ceiling"):
        analyze(source, budget=GraphBudget(edges=1))


def test_output_cap_does_not_change_full_plan_digest(source):
    all_rows = analyze(source)
    limited = analyze(source, budget=GraphBudget(reported_components=1))
    assert limited["component_output_truncated"]
    assert limited["candidate_plan_digest"] == all_rows["candidate_plan_digest"]


def test_cli_real_integration(source, capsys):
    from skeleton.__main__ import main as root_main
    assert root_main(["orphan-source-graph", "--root", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["component_count"] > 0
    assert main(["--root", str(source), "--max-entries", "1"]) == 3
