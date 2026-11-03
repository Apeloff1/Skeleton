"""Single integrated CLI entrypoint and closed command admission."""
import json
import pytest

from skeleton.game.gameplay.ridge_rescue.studio_cli import main, catalog


def test_catalog_contains_all_real_user_reachable_verticals():
    result = catalog()
    assert result["schema"] == "ridge.rescue.launcher.v1"
    assert result["release_certified"] is False
    names = {item["id"] for item in result["commands"]}
    assert {"rescue", "campaign", "missions", "journal", "package", "routebook",
            "tactics", "workbench", "league", "league-demo", "acceptance"} <= names
    assert len(names) == len(result["commands"])


def test_list_and_real_source_inspection(capsys):
    assert main(["list"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["offline"] is True
    assert main(["routebook", "inspect"]) == 0
    routes = json.loads(capsys.readouterr().out)
    assert len(routes["tracks"]) == 2
    assert main(["league", "rank"]) == 0
    league = json.loads(capsys.readouterr().out)
    assert league["entries"] == 0


def test_unknown_subsystem_is_not_dynamic_import():
    with pytest.raises(SystemExit) as exc:
        main(["os.system", "whoami"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        main(["../../module", "run"])
    assert exc.value.code == 2
