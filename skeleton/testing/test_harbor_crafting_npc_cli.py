"""NPC report and forecast CLI round-trip."""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.game.gameplay.harbor_crafting import canonical, export_bundle, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD, main


def _save(root: Path, name: str, value: object) -> str:
    path = root / name
    path.write_bytes(canonical(value))
    return str(path)


def test_npc_cli_report_and_forecast(tmp_path, capfd):
    bundle = export_bundle(load_source(DEFAULT_WORLD), [])
    path = _save(tmp_path, "bundle.json", bundle)
    assert main(["npc-report", "--bundle", path]) == 0
    report = json.loads(capfd.readouterr().out)
    assert report["entries"][0]["tick"] == 0
    report_path = _save(tmp_path, "report.json", report)
    assert main(["verify-npc-report", "--report", report_path]) == 0
    assert json.loads(capfd.readouterr().out)["verified"] is True
    assert main(["npc-forecast", "--bundle", path, "--tick", "3"]) == 0
    forecast = json.loads(capfd.readouterr().out)
    assert len(forecast["entries"]) == 3
    forecast_path = _save(tmp_path, "forecast.json", forecast)
    assert main(["verify-npc-forecast", "--report", forecast_path]) == 0
    assert json.loads(capfd.readouterr().out)["verified"] is True
