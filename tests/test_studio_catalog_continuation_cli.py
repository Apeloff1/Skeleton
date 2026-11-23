"""CLI continuation shares canonical source snapshot guard with Jeeves."""
from __future__ import annotations

import json

import pytest

from scripts.studio_ecosystem_cli import main


def test_cli_catalog_first_and_followup_page(capsys):
    assert main(["--walk-audit-catalog", "--walk-audit-batch-size", "1"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["continuation"]["offset"] == 1
    assert main([
        "--walk-audit-catalog", "--walk-audit-offset", "1",
        "--walk-audit-batch-size", "1",
        "--walk-audit-expected-digest", first["catalog_digest"],
    ]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["page_offset"] == 1
    assert second["catalog_digest"] == first["catalog_digest"]


@pytest.mark.parametrize("args", [
    ["--walk-audit-catalog", "--walk-audit-offset", "1"],
    ["--walk-audit-catalog", "--walk-audit-offset", "1",
     "--walk-audit-expected-digest", "0" * 64],
    ["--walk-audit-expected-digest", "0" * 64],
])
def test_cli_invalid_continuation_fails_closed(args, capsys):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert not capsys.readouterr().out


def test_cli_no_implicit_catalog_auth_from_play_mode(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--play-walk", "--walk-audit-expected-digest", "0" * 64])
    assert exc.value.code == 2
    assert not capsys.readouterr().out
