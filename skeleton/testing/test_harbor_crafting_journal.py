"""End-to-end and adversarial journal custody, gameplay, CLI and export."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
    verify_bundle,
)
from skeleton.game.gameplay.harbor_crafting_journal import (
    MAX_ACTIONS_PER_REVISION, MAX_REVISIONS, append_journal, create_journal,
    journal_at, journal_audit, journal_head, rewind_journal, verify_journal,
)

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def world():
    return load_source(WORLD)


def start():
    return create_journal(export_bundle(world(), []))


def extend(journal, actions):
    return append_journal(
        journal, actions, expected_journal_digest=journal["journal_digest"],
    )


def complete():
    root = start()
    middle = extend(root, demo_actions()[:10])
    finished = extend(middle, demo_actions()[10:])
    return root, middle, finished


def test_playable_campaign_survives_journal_restart_and_byte_identical_export():
    root, middle, finished = complete()
    recovered = decode(canonical(finished))
    assert journal_head(recovered) == export_bundle(world(), demo_actions(), require_win=True)
    assert verify_bundle(journal_head(recovered), require_win=True)["ending"] == "beacon"
    assert verify_journal(recovered) == {
        "source_digest": finished["root"]["source_digest"],
        "terminal_digest": finished["head_terminal_digest"],
        "bundle_digest": finished["head_bundle_digest"],
        "tick": len(demo_actions()), "ending": "beacon", "revisions": 2,
    }
    assert journal_at(finished, 0) == root["root"]
    assert journal_at(finished, 1) == journal_head(middle)
    assert journal_at(finished, 2) == journal_head(finished)


def test_rewind_and_new_choice_are_earned_replay_futures():
    before_choice = extend(start(), demo_actions()[:-1])
    beacon = extend(before_choice, [{"op": "choose", "choice": "signal"}])
    shelter = extend(before_choice, [{"op": "choose", "choice": "shelter"}])
    assert journal_head(beacon)["state"]["ending"] == "beacon"
    assert journal_head(shelter)["state"]["ending"] == "safe_harbor"
    assert beacon["head_terminal_digest"] != shelter["head_terminal_digest"]
    rewound = rewind_journal(beacon, 1, expected_journal_digest=beacon["journal_digest"])
    assert rewound == before_choice
    assert beacon != rewound


def test_reject_stale_leases_without_mutating_saved_history():
    original = start()
    snapshot = deepcopy(original)
    for wrong in ("", "0" * 64, None, True):
        with pytest.raises(HarborError, match="stale journal"):
            append_journal(original, [{"op": "wait"}], expected_journal_digest=wrong)
        with pytest.raises(HarborError, match="stale journal"):
            rewind_journal(original, 0, expected_journal_digest=wrong)
    assert original == snapshot


@pytest.mark.parametrize("bad", [
    [], [{"op": "wait"}] * (MAX_ACTIONS_PER_REVISION + 1),
    [{"op": "teleport"}], [{"op": "move", "direction": "up"}],
    [{"op": "wait", "extra": "forged"}], None, "wait",
])
def test_reject_invalid_or_unbounded_continuations(bad):
    journal = start()
    with pytest.raises(HarborError):
        append_journal(journal, bad, expected_journal_digest=journal["journal_digest"])


@pytest.mark.parametrize("mutation", [
    lambda j: j["root"]["state"].update({"coins": 999}),
    lambda j: j["revisions"][0]["actions"][0].update({"op": "gather"}),
    lambda j: j["revisions"][0].update({"terminal_digest": "0" * 64}),
    lambda j: j["revisions"][0].update({"bundle_digest": "0" * 64}),
    lambda j: j["revisions"][0].update({"index": True}),
    lambda j: j["revisions"][0].update({"parent": "0" * 64}),
    lambda j: j.update({"head_bundle_digest": "0" * 64}),
    lambda j: j["revisions"][0].update({"actions": []}),
])
def test_reject_tampering_even_when_outer_digest_is_recomputed(mutation):
    journal = extend(start(), demo_actions()[:3])
    mutation(journal)
    for revision in journal["revisions"]:
        revision["revision_digest"] = digest({
            k: v for k, v in revision.items() if k != "revision_digest"
        })
    journal["journal_digest"] = digest({
        k: v for k, v in journal.items() if k != "journal_digest"
    })
    with pytest.raises(HarborError):
        verify_journal(journal)


def test_revision_and_tick_budgets_fail_closed():
    journal = start()
    for _ in range(MAX_REVISIONS):
        journal = extend(journal, [{"op": "wait"}])
    with pytest.raises(HarborError, match="revision budget"):
        extend(journal, [{"op": "wait"}])
    assert verify_journal(journal)["revisions"] == MAX_REVISIONS
    for index in (-1, True, MAX_REVISIONS + 1, "1"):
        with pytest.raises(HarborError):
            journal_at(journal, index)


def test_audit_is_replay_derived_and_has_no_authority_to_change_game():
    root, middle, finished = complete()
    report = journal_audit(finished)
    assert [e["tick"] for e in report["entries"]] == [0, 10, 18]
    assert report["entries"][-1]["ending"] == "beacon"
    assert report["entries"][0]["revision_digest"] is None
    assert report["entries"][1]["revision_digest"] == middle["revisions"][0]["revision_digest"]
    assert journal_head(root)["state"]["tick"] == 0


def _cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "scripts.game.harbor_crafting", *args],
        capture_output=True, check=False,
    )


def test_cli_create_append_verify_rewind_and_export(tmp_path):
    root = export_bundle(world(), [])
    source = tmp_path / "root.json"
    source.write_bytes(canonical(root))
    initialized = _cli("journal-init", "--bundle", str(source))
    assert initialized.returncode == 0, initialized.stderr.decode()
    journal = decode(initialized.stdout)
    journal_file = tmp_path / "journal.json"
    journal_file.write_bytes(initialized.stdout)
    actions = tmp_path / "actions.json"
    actions.write_bytes(canonical(demo_actions()))
    appended = _cli(
        "journal-append", "--journal", str(journal_file),
        "--actions", str(actions), "--expected-journal-digest", journal["journal_digest"],
        "--require-win",
    )
    assert appended.returncode == 0, appended.stderr.decode()
    finished = decode(appended.stdout)
    journal_file.write_bytes(appended.stdout)
    verified = _cli("journal-verify", "--journal", str(journal_file))
    assert verified.returncode == 0, verified.stderr.decode()
    assert decode(verified.stdout)["ending"] == "beacon"
    exported = _cli("journal-export", "--journal", str(journal_file))
    assert exported.returncode == 0, exported.stderr.decode()
    assert decode(exported.stdout) == export_bundle(world(), demo_actions())
    audited = _cli("journal-audit", "--journal", str(journal_file))
    assert audited.returncode == 0, audited.stderr.decode()
    assert decode(audited.stdout)["entries"][-1]["tick"] == 18
    rewound = _cli(
        "journal-rewind", "--journal", str(journal_file), "--revision-index", "0",
        "--expected-journal-digest", finished["journal_digest"],
    )
    assert rewound.returncode == 0, rewound.stderr.decode()
    assert decode(rewound.stdout) == journal


def test_cli_stale_lease_does_not_emit_false_success(tmp_path):
    journal = start()
    path = tmp_path / "journal.json"
    path.write_bytes(canonical(journal))
    actions = tmp_path / "actions.json"
    actions.write_bytes(canonical([{"op": "wait"}]))
    failed = _cli(
        "journal-append", "--journal", str(path), "--actions", str(actions),
        "--expected-journal-digest", "0" * 64,
    )
    assert failed.returncode == 2
    assert failed.stdout == b""
    assert decode(path.read_bytes()) == journal
