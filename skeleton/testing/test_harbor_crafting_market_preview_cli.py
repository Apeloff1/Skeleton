"""Market preview and apply CLI end-to-end acceptance."""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.game.gameplay.harbor_crafting import canonical, demo_actions, export_bundle, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD, main


def _save(root: Path, name: str, value: object) -> str:
    path = root / name
    path.write_bytes(canonical(value))
    return str(path)


def test_cli_market_preview_and_apply(tmp_path, capfd):
    actions = demo_actions()
    bundle = export_bundle(load_source(DEFAULT_WORLD), actions[:-1])
    bundle_path = _save(tmp_path, "bundle.json", bundle)
    suffix_path = _save(tmp_path, "suffix.json", [actions[-1]])
    assert main(["market-preview", "--bundle", bundle_path, "--actions", suffix_path]) == 0
    preview = json.loads(capfd.readouterr().out)
    preview_path = _save(tmp_path, "preview.json", preview)
    assert main(["verify-market-preview", "--preview", preview_path]) == 0
    assert json.loads(capfd.readouterr().out)["verified"] is True
    assert main([
        "market-apply", "--preview", preview_path,
        "--expected-terminal-digest", bundle["terminal_digest"], "--require-win",
    ]) == 0
    assert json.loads(capfd.readouterr().out)["totals"]["ending"] == "beacon"
    assert main(["market-apply", "--preview", preview_path]) == 2
    assert "required" in capfd.readouterr().err
