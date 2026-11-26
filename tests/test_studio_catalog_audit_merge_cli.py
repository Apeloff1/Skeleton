"""CLI catalog merge rejects untrusted JSON before source replay."""
from __future__ import annotations

from io import BytesIO
import json
import sys

import pytest

from scripts.studio_ecosystem_cli import main
from skeleton.ai.game_builder import studio_ecosystem_walk_coverage_batch as batch


class _Input:
    def __init__(self, data: bytes):
        self.buffer = BytesIO(data)


def test_cli_merge_canonical_page(monkeypatch, capsys):
    page = batch.audit_catalog_walk_choices(authorized=True, limit=1)
    monkeypatch.setattr(sys, "stdin", _Input(json.dumps([page]).encode()))
    assert main(["--walk-audit-aggregate-stdin"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["pages_verified"] == 1
    assert receipt["catalog_digest"] == page["catalog_digest"]
    assert receipt["release_certified"] is False


@pytest.mark.parametrize("data", [
    b"[]", b"[{}]", b"[NaN]", b'[{"schema":"a","schema":"b"}]',
    b"x" * 131073,
])
def test_cli_merge_rejects_bad_json_and_budgets(data, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Input(data))
    with pytest.raises(SystemExit) as exc:
        main(["--walk-audit-aggregate-stdin"])
    assert exc.value.code == 2
    assert not capsys.readouterr().out


def test_cli_merge_rejects_ambiguous_mode(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Input(b"[]"))
    with pytest.raises(SystemExit) as exc:
        main(["--walk-audit-aggregate-stdin", "--walk-audit-catalog"])
    assert exc.value.code == 2
    assert not capsys.readouterr().out
