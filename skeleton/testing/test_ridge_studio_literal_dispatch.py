"""Recovered Cinder Ridge launcher must remain lazy and literal."""
from unittest.mock import patch

import pytest

from skeleton.game.gameplay.ridge_rescue import studio_cli


def test_catalog_and_dispatch_cover_the_same_commands():
    assert set(studio_cli.COMMANDS) == set(studio_cli._ENTRYPOINTS)
    with patch.object(studio_cli.importlib, "import_module", side_effect=AssertionError):
        assert studio_cli.catalog()["offline"] is True
        with pytest.raises(SystemExit) as caught:
            studio_cli.main(["unknown-subsystem"])
        assert caught.value.code == 2


@pytest.mark.parametrize("name", sorted(studio_cli.COMMANDS))
def test_dispatch_imports_exactly_one_reviewed_module(name):
    module_name = studio_cli.COMMANDS[name][0]
    with patch.object(studio_cli.importlib, "import_module") as load:
        load.return_value.main.return_value = 17
        assert studio_cli.main([name, "--flag", "value"]) == 17
        load.assert_called_once_with("skeleton.game.gameplay.ridge_rescue." + module_name)
        load.return_value.main.assert_called_once_with(["--flag", "value"])
