"""Portable convoy package and historical CAS journal acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy_package import (
    build_convoy_package, verify_convoy_package, play_convoy_package,
    verify_convoy_package_play, resume_convoy_package,
)
from skeleton.game.gameplay.harbor_crafting_convoy_journal import (
    create_convoy_journal, append_convoy_journal, verify_convoy_journal,
    convoy_journal_at,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def setup():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_convoy.json").read_bytes())
    actions = demo_actions()[:12] + [
        {"op": "escort"}, {"op": "move", "direction": "east"},
        {"op": "escort"}, {"op": "strike"},
        {"op": "move", "direction": "east"}, {"op": "escort"},
        {"op": "move", "direction": "east"}, {"op": "escort"},
    ]
    return source, board, actions


def test_package_play_verify_resume_and_portable_replay():
    source, board, actions = setup()
    package = build_convoy_package("original_convoy", source, board)
    assert verify_convoy_package(decode(canonical(package)))["id"] == "original_convoy"
    partial = play_convoy_package(package, actions[:15])
    final = resume_convoy_package(
        partial, actions[15:], expected_digest=partial["play_digest"],
        require_complete=True,
    )
    assert final == play_convoy_package(package, actions, require_complete=True)
    assert verify_convoy_package_play(decode(canonical(final)), require_complete=True)["complete"]
    with pytest.raises(HarborError, match="stale"):
        resume_convoy_package(partial, actions[15:], expected_digest="0" * 64)
    with pytest.raises(HarborError, match="terminal"):
        resume_convoy_package(final, [{"op": "wait"}],
                              expected_digest=final["play_digest"])


def test_package_and_play_resealed_forgery_rejected():
    source, board, actions = setup()
    package = build_convoy_package("original_convoy", source, board)
    altered = deepcopy(package)
    altered["board"]["hull"] = 20
    with pytest.raises(HarborError, match="digest"):
        verify_convoy_package(altered)
    play = play_convoy_package(package, actions)
    forged = deepcopy(play)
    forged["report"]["state"]["bounty"] = 900
    forged["report"]["report_digest"] = digest({
        k: v for k, v in forged["report"].items() if k != "report_digest"
    })
    forged["play_digest"] = digest({
        k: v for k, v in forged.items() if k != "play_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_convoy_package_play(forged)


def test_journal_append_historical_checkpoint_fork_and_tamper():
    source, board, actions = setup()
    package = build_convoy_package("original_convoy", source, board)
    journal = create_convoy_journal(package)
    assert verify_convoy_journal(journal)["entries"] == 0
    chunks = [actions[:12], actions[12:15], actions[15:]]
    for chunk in chunks:
        journal = append_convoy_journal(
            journal, chunk, expected_digest=journal["journal_digest"],
        )
    status = verify_convoy_journal(decode(canonical(journal)))
    assert status["complete"] and status["entries"] == 3 and status["actions"] == 20
    early = convoy_journal_at(journal, 1)
    assert verify_convoy_journal(early)["actions"] == 12
    fork = append_convoy_journal(
        early, [{"op": "escort"}], expected_digest=early["journal_digest"],
    )
    assert fork["head"] != journal["head"]
    with pytest.raises(HarborError, match="stale"):
        append_convoy_journal(early, [{"op": "escort"}], expected_digest=journal["journal_digest"])
    with pytest.raises(HarborError, match="terminal"):
        append_convoy_journal(journal, [{"op": "wait"}], expected_digest=journal["journal_digest"])
    forged = deepcopy(journal)
    forged["entries"][1]["report_digest"] = "f" * 64
    forged["entries"][1]["digest"] = digest({
        k: v for k, v in forged["entries"][1].items() if k != "digest"
    })
    forged["entries"][2]["previous"] = forged["entries"][1]["digest"]
    forged["entries"][2]["digest"] = digest({
        k: v for k, v in forged["entries"][2].items() if k != "digest"
    })
    forged["journal_digest"] = digest({
        k: v for k, v in forged.items() if k != "journal_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_convoy_journal(forged)


def test_cli_package_play_and_journal_end_to_end(tmp_path):
    source, board, actions = setup()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        proc = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr.decode()
        return decode(proc.stdout)
    package = call(
        "convoy-package-build",
        "--source", str(FIXTURES / "harbor_lantern_quay.json"),
        "--convoy-board", str(FIXTURES / "harbor_lantern_quay_convoy.json"),
    )
    package_path = write("package", package)
    assert call("convoy-package-verify", "--convoy-package", package_path)["verified"]
    play = call(
        "convoy-package-play", "--convoy-package", package_path,
        "--actions", write("actions", actions), "--require-all",
    )
    assert call(
        "convoy-package-verify-play", "--convoy-play", write("play", play),
        "--require-all",
    )["complete"]
    partial = call(
        "convoy-package-play", "--convoy-package", package_path,
        "--actions", write("partial-actions", actions[:15]),
    )
    resumed = call(
        "convoy-package-resume", "--convoy-play", write("partial", partial),
        "--actions", write("rest", actions[15:]),
        "--expected-convoy-play-digest", partial["play_digest"], "--require-all",
    )
    assert resumed == play
    journal = call("convoy-journal-init", "--convoy-package", package_path)
    for index, chunk in enumerate((actions[:12], actions[12:15], actions[15:])):
        journal = call(
            "convoy-journal-append", "--convoy-journal", write("journal", journal),
            "--actions", write("chunk" + str(index), chunk),
            "--expected-convoy-journal-digest", journal["journal_digest"],
        )
    assert call("convoy-journal-verify", "--convoy-journal",
                write("final-journal", journal))["complete"]
    historic = call("convoy-journal-at", "--convoy-journal",
                    write("journal-history", journal), "--convoy-revision-index", "1")
    assert verify_convoy_journal(historic)["actions"] == 12
