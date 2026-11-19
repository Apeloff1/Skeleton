"""Recovered operator entry-points and real assurance suite accounting."""
import ast
import configparser
import json
from pathlib import Path
import sys
import tomllib
from types import ModuleType

import pytest

from skeleton.__main__ import main
from skeleton.app import local_source_assurance as assurance
from skeleton.app.recovered_evidence import EvidenceError

ROOT=Path(__file__).resolve().parents[2]
OWNERS=(
    ("dragon-almanac","skeleton.ai.game_builder.dragon_almanac_cli"),
    ("dragon-technical-sources","skeleton.ai.game_builder.dragon_technical_source_cli"),
    ("original-native-evolution","skeleton.ai.game_builder.native_evolution_cli"),
    ("original-native-game","skeleton.ai.game_builder.native_game_cli"),
    ("original-native-portfolio","skeleton.ai.game_builder.native_portfolio_cli"),
    ("studio-competitive-review","skeleton.ai.game_builder.competitive_27page_review_cli"),
    ("studio-battle-review","skeleton.ai.game_builder.competitive_battle_review_cli"),
    ("studio-competitive-watch","skeleton.ai.game_builder.competitive_watch_cli"),
    ("studio-rival-review","skeleton.ai.game_builder.rival_watch_cli"),
    ("cross-era-game-project","skeleton.ai.runtime.game_project_cli"),
    ("local-trust-gates","skeleton.ai.runtime.operational_ai.trust_gates.cli"),
    ("local-source-assurance","skeleton.app.local_source_assurance"),
)


@pytest.mark.parametrize("command,module",OWNERS)
def test_transparent_dispatch(monkeypatch,command,module):
    imported=ModuleType(module)
    calls=[]
    def execute(argv):
        calls.append(argv)
        return 19
    imported.main=execute
    monkeypatch.setitem(sys.modules,module,imported)
    assert main([command,"--owner-only","literal"])==19
    assert calls==[["--owner-only","literal"]]


@pytest.mark.parametrize("command,module",OWNERS)
def test_metadata_and_canonical_source(command,module):
    if not (ROOT/"pyproject.toml").is_file():
        pytest.skip("source metadata unavailable")
    py=tomllib.loads((ROOT/"pyproject.toml").read_text(encoding="utf-8"))
    cfg=configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT/"setup.cfg",encoding="utf-8")
    legacy=dict(x.strip().split(" = ",1) for x in cfg["options.entry_points"]["console_scripts"].splitlines() if x.strip())
    key="skeleton-"+command
    assert py["project"]["scripts"][key]==legacy[key]==module+":main"
    tree=ast.parse(ROOT.joinpath(*module.split(".")).with_suffix(".py").read_bytes())
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main"]
    assert len(functions)==1
    assert functions[0].args.args[0].arg=="argv"
    assert functions[0].args.defaults


@pytest.mark.parametrize("command",["dragon-almanac","dragon-technical-sources",
    "original-native-evolution","original-native-game","original-native-portfolio"])
def test_actual_older_owner_help(command,capsys):
    with pytest.raises(SystemExit) as e:
        main([command,"--help"])
    assert e.value.code==0
    assert "usage:" in capsys.readouterr().out.lower()


def test_inventory_does_not_execute(monkeypatch):
    monkeypatch.setattr(assurance,"_execute",lambda name:pytest.fail("inventory ran suite"))
    assert assurance.inventory()["expected_total"]==5100
    assert not assurance.inventory()["executed"]


def test_real_trust_owner_repeat():
    report=assurance.qualify(["trust-gates"],authorized=True,repeat=True)
    assert report["accounted_first_pass_cases"]==240
    assert report["selected_source_suites_passed"]
    assert report["suites"][0]["repeat_matched"]
    assert not report["complete_source_assurance_passed"]


def test_actual_complete_fixture_set():
    report=assurance.qualify(assurance.SUITES,authorized=True)
    assert report["complete_source_assurance_passed"]
    assert report["accounted_first_pass_cases"]==5100
    assert report["passed_first_pass_cases"]==5100
    assert report["physical_device_tested"] is False


def test_blocked_suite_preserves_other_accounting(monkeypatch):
    def execute(name):
        if name=="guarded-request":
            return {"total":384,"passed":383,"failed":1}
        raise RuntimeError("private source path")
    monkeypatch.setattr(assurance,"_execute",execute)
    result=assurance.qualify(["guarded-request","durable-jobs"],authorized=True)
    assert result["accounted_first_pass_cases"]==384
    assert result["failed_first_pass_cases"]==1
    assert result["suites"][1]["state"]=="blocked"
    assert "private source" not in json.dumps(result)
    assert not result["selected_source_suites_passed"]


def test_no_implicit_execution(monkeypatch):
    monkeypatch.setattr(assurance,"_execute",lambda name:pytest.fail("unauthorized suite"))
    with pytest.raises(PermissionError):
        assurance.qualify(["trust-gates"],authorized=False)
    with pytest.raises(EvidenceError):
        assurance.qualify(["trust-gates","trust-gates"],authorized=True)


def test_installed_inventory(capsys):
    assert main(["local-source-assurance","inventory"])==0
    assert json.loads(capsys.readouterr().out)["expected_total"]==5100
