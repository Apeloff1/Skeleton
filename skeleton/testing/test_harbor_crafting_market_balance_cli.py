"""End-to-end economy authoring and replay verification CLI."""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.game.gameplay.harbor_crafting import canonical, digest, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD, main


def test_cli_market_balance_roundtrip(tmp_path: Path, capfd):
    source = load_source(DEFAULT_WORLD)
    edits = tmp_path / "edits.json"
    edits.write_bytes(canonical([{"op": "merchant_price", "price": 3}]))
    assert main([
        "market-balance", "--edits", str(edits),
        "--expected-source-digest", digest(source),
    ]) == 0
    comparison = json.loads(capfd.readouterr().out)
    assert comparison["after"]["ending"] == "beacon"
    path = tmp_path / "comparison.json"
    path.write_bytes(canonical(comparison))
    assert main(["verify-market-balance", "--comparison", str(path)]) == 0
    assert json.loads(capfd.readouterr().out)["verified"] is True


def test_cli_market_balance_requires_lease(capfd):
    assert main(["market-balance"]) == 2
    assert "required" in capfd.readouterr().err
