"""CLI-level source -> edit -> runtime -> save -> package -> replay acceptance."""
from __future__ import annotations

import copy
import json

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign import normalize_campaign, original_campaign


def _run(capsys, *args):
    status = main(list(args))
    output = capsys.readouterr()
    return status, json.loads(output.out) if output.out else json.loads(output.err)


def test_authoring_and_portable_delivery_replay_through_main_cli(capsys):
    original = original_campaign()
    status, authored = _run(capsys, "combat-campaign-author", "demo")
    assert status == 0
    assert authored["source_digest"] if "source_digest" in authored else authored["after_digest"]
    assert authored["before_digest"] == dig(normalize_campaign(original))

    status, verified_edit = _run(
        capsys, "combat-campaign-author", "verify",
        "--source-json", json.dumps(original),
        "--receipt-json", json.dumps(authored),
    )
    assert status == 0 and verified_edit == authored

    status, played = _run(
        capsys, "combat-campaign", "simulate",
        "--source-json", json.dumps(authored["source"]),
    )
    assert status == 0 and played == authored["preview_session"]

    status, bundle = _run(
        capsys, "combat-campaign-package", "pack",
        "--source-json", json.dumps(authored["source"]),
        "--session-json", json.dumps(played),
    )
    assert status == 0
    assert bundle["snapshot"]["state"]["phase"] == "won"

    status, verified_bundle = _run(
        capsys, "combat-campaign-package", "verify",
        "--package-json", json.dumps(bundle),
    )
    assert status == 0 and verified_bundle == bundle

    status, resumed = _run(
        capsys, "combat-campaign-package", "resume",
        "--package-json", json.dumps(bundle),
    )
    assert status == 0 and resumed == bundle


def test_checkpoint_demo_resume_and_replay_via_cli(capsys):
    status, partial = _run(capsys, "combat-campaign-package", "demo")
    assert status == 0
    assert partial["manifest"]["phase"] == "active"
    assert partial["manifest"]["next_index"] == 1

    status, terminal = _run(
        capsys, "combat-campaign-package", "resume",
        "--package-json", json.dumps(partial),
    )
    assert status == 0
    assert terminal["manifest"]["phase"] == "won"
    assert terminal["manifest"]["next_index"] == 2

    status, checked = _run(
        capsys, "combat-campaign-package", "verify",
        "--package-json", json.dumps(terminal),
    )
    assert status == 0 and checked == terminal


def test_cli_tamper_and_stale_source_fail_without_releasing_rewards(capsys):
    status, bundle = _run(capsys, "combat-campaign-package", "demo")
    assert status == 0
    bad = copy.deepcopy(bundle)
    bad["snapshot"]["state"]["currency"] += 1000
    status, rejected = _run(
        capsys, "combat-campaign-package", "resume",
        "--package-json", json.dumps(bad),
    )
    assert status == 2 and rejected["ok"] is False

    source = original_campaign()
    edits = [{"kind": "set-reward", "encounter_id": "reed_watch", "value": 11}]
    status, rejected = _run(
        capsys, "combat-campaign-author", "edit",
        "--source-json", json.dumps(source),
        "--operations-json", json.dumps(edits),
        "--expected-digest", "0" * 64,
    )
    assert status == 2 and rejected["ok"] is False
