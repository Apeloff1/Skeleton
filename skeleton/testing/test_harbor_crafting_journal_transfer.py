"""Original source through playable journal, mission and package export."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_journal import (
    append_journal, create_journal, journal_head,
)
from skeleton.game.gameplay.harbor_crafting_journal_transfer import (
    export_journal_package_play, verify_journal_package_play,
)
from skeleton.game.gameplay.harbor_crafting_package import (
    build_package, verify_package_play,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
WORLD = ROOT / "harbor_lantern_quay.json"
BOARD = ROOT / "harbor_lantern_quay_missions.json"


def inputs():
    source = load_source(WORLD)
    board = decode(BOARD.read_bytes())
    return source, board


def game_journal(source, actions):
    root = create_journal(export_bundle(source, []))
    if not actions:
        return root
    return append_journal(
        root, actions, expected_journal_digest=root["journal_digest"],
    )


def test_full_earned_campaign_transfers_to_replayable_original_package():
    source, board = inputs()
    package = build_package(source, board)
    journal = game_journal(source, demo_actions())
    transfer = export_journal_package_play(journal, package)
    assert transfer["package_play"]["report"]["bundle"] == journal_head(journal)
    assert verify_package_play(transfer["package_play"])["ending"] == "beacon"
    result = verify_journal_package_play(decode(canonical(transfer)))
    assert result["ending"] == "beacon"
    assert result["terminal_digest"] == journal["head_terminal_digest"]
    assert result["package_digest"] == package["package_digest"]


def test_partial_session_can_be_packaged_without_fabricated_victory():
    source, board = inputs()
    package = build_package(source, board)
    journal = game_journal(source, demo_actions()[:8])
    transfer = export_journal_package_play(journal, package)
    assert verify_journal_package_play(transfer)["ending"] is None
    with pytest.raises(HarborError):
        export_journal_package_play(journal, package, require_all=True)


def test_unrelated_world_is_rejected_before_play():
    source, board = inputs()
    package = build_package(source, board)
    altered = deepcopy(source)
    altered["id"] = "different_original_world"
    journal = game_journal(altered, [])
    with pytest.raises(HarborError, match="world mismatch"):
        export_journal_package_play(journal, package)


@pytest.mark.parametrize("mutation", [
    lambda t: t.update({"terminal_digest": "0" * 64}),
    lambda t: t.update({"package_digest": "0" * 64}),
    lambda t: t["package_play"]["report"]["bundle"]["state"].update({"coins": 999}),
    lambda t: t["journal"]["root"]["state"].update({"coins": 999}),
    lambda t: t.update({"journal_digest": "0" * 64}),
])
def test_resealed_transfer_does_not_bypass_replay(mutation):
    source, board = inputs()
    transfer = export_journal_package_play(
        game_journal(source, demo_actions()), build_package(source, board),
    )
    mutation(transfer)
    transfer["transfer_digest"] = digest({
        key: value for key, value in transfer.items() if key != "transfer_digest"
    })
    with pytest.raises(HarborError):
        verify_journal_package_play(transfer)


def test_cli_original_game_to_portable_journal_play(tmp_path):
    source, board = inputs()
    journal = game_journal(source, demo_actions())
    package = build_package(source, board)
    journal_path = tmp_path / "journal.json"
    package_path = tmp_path / "package.json"
    journal_path.write_bytes(canonical(journal))
    package_path.write_bytes(canonical(package))
    cmd = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    produced = subprocess.run(
        cmd + ["journal-package-play", "--journal", str(journal_path),
               "--package", str(package_path)],
        capture_output=True, check=False,
    )
    assert produced.returncode == 0, produced.stderr.decode()
    transfer = decode(produced.stdout)
    assert transfer["terminal_digest"] == journal["head_terminal_digest"]
    saved = tmp_path / "transfer.json"
    saved.write_bytes(produced.stdout)
    checked = subprocess.run(
        cmd + ["journal-verify-package-play", "--play", str(saved)],
        capture_output=True, check=False,
    )
    assert checked.returncode == 0, checked.stderr.decode()
    assert decode(checked.stdout)["ending"] == "beacon"


def test_empty_journal_root_is_valid_but_empty_revision_is_rejected():
    source, _ = inputs()
    root = game_journal(source, [])
    assert journal_head(root)["source_digest"] == root["root"]["source_digest"]
    with pytest.raises(HarborError, match="action budget"):
        append_journal(root, [], expected_journal_digest=root["journal_digest"])
