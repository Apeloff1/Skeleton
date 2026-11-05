"""Cross-device history exchange, source binding and conflict acceptance."""
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
    append_journal, create_journal, journal_head, verify_journal,
)
from skeleton.game.gameplay.harbor_crafting_journal_merge import (
    compare_journals, fast_forward_journal, verify_journal_comparison,
)

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def root():
    return create_journal(export_bundle(load_source(WORLD), []))


def append(journal, actions):
    return append_journal(
        journal, actions, expected_journal_digest=journal["journal_digest"],
    )


def histories():
    base = root()
    prefix = append(base, demo_actions()[:-1])
    beacon = append(prefix, [{"op": "choose", "choice": "signal"}])
    shelter = append(prefix, [{"op": "choose", "choice": "shelter"}])
    return base, prefix, beacon, shelter


def test_identical_and_prefix_fast_forward_are_replay_verified():
    base, prefix, beacon, shelter = histories()
    report = compare_journals(prefix, beacon)
    assert report["relation"] == "left_ancestor"
    assert report["common_revisions"] == 1
    assert verify_journal_comparison(decode(canonical(report)))["right_revisions"] == 2
    assert fast_forward_journal(
        prefix, beacon, expected_journal_digest=prefix["journal_digest"],
    ) == beacon
    assert compare_journals(beacon, prefix)["relation"] == "right_ancestor"
    assert compare_journals(beacon, deepcopy(beacon))["relation"] == "identical"
    assert compare_journals(base, beacon)["relation"] == "left_ancestor"
    assert verify_journal(beacon)["ending"] == "beacon"
    assert verify_journal(shelter)["ending"] == "safe_harbor"


def test_conflicting_choices_are_never_automatically_merged():
    _, prefix, beacon, shelter = histories()
    report = compare_journals(beacon, shelter)
    assert report["relation"] == "diverged"
    assert report["common_revisions"] == 1
    with pytest.raises(HarborError, match="conflict"):
        fast_forward_journal(
            beacon, shelter, expected_journal_digest=beacon["journal_digest"],
        )
    with pytest.raises(HarborError, match="conflict"):
        fast_forward_journal(
            beacon, prefix, expected_journal_digest=beacon["journal_digest"],
        )
    assert journal_head(beacon)["state"]["ending"] == "beacon"
    assert journal_head(shelter)["state"]["ending"] == "safe_harbor"


def test_optimistic_lease_must_be_exact_and_does_not_modify_input():
    _, prefix, beacon, _ = histories()
    original = deepcopy(prefix)
    for stale in ("", "0" * 64, None, True):
        with pytest.raises(HarborError, match="stale"):
            fast_forward_journal(
                prefix, beacon, expected_journal_digest=stale,
            )
    assert prefix == original


def test_different_original_worlds_are_rejected():
    source = load_source(WORLD)
    source["id"] = "another_original_world"
    other = create_journal(export_bundle(source, []))
    with pytest.raises(HarborError, match="root"):
        compare_journals(root(), other)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update({"relation": "identical"}),
    lambda p: p.update({"common_revisions": 99}),
    lambda p: p.update({"left_terminal_digest": "0" * 64}),
    lambda p: p["left"]["revisions"][0]["actions"][0].update({"op": "gather"}),
    lambda p: p["right"]["root"]["state"].update({"coins": 999}),
    lambda p: p.update({"left_digest": "0" * 64}),
])
def test_resealed_report_still_requires_real_replay(mutation):
    _, prefix, beacon, _ = histories()
    report = compare_journals(prefix, beacon)
    mutation(report)
    report["comparison_digest"] = digest({
        k: v for k, v in report.items() if k != "comparison_digest"
    })
    with pytest.raises(HarborError):
        verify_journal_comparison(report)


def _cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "scripts.game.harbor_crafting", *args],
        capture_output=True, check=False,
    )


def test_cli_cross_device_compare_verify_and_fast_forward(tmp_path):
    _, prefix, beacon, shelter = histories()
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_bytes(canonical(prefix))
    right.write_bytes(canonical(beacon))
    result = _cli(
        "journal-compare", "--journal", str(left), "--other-journal", str(right),
    )
    assert result.returncode == 0, result.stderr.decode()
    report = decode(result.stdout)
    assert report["relation"] == "left_ancestor"
    report_path = tmp_path / "comparison.json"
    report_path.write_bytes(result.stdout)
    checked = _cli("journal-verify-comparison", "--comparison", str(report_path))
    assert checked.returncode == 0, checked.stderr.decode()
    assert decode(checked.stdout)["relation"] == "left_ancestor"
    advanced = _cli(
        "journal-fast-forward", "--journal", str(left), "--other-journal", str(right),
        "--expected-journal-digest", prefix["journal_digest"],
    )
    assert advanced.returncode == 0, advanced.stderr.decode()
    assert decode(advanced.stdout) == beacon
    right.write_bytes(canonical(shelter))
    refused = _cli(
        "journal-fast-forward", "--journal", str(left), "--other-journal", str(right),
        "--expected-journal-digest", "0" * 64,
    )
    assert refused.returncode == 2
    assert refused.stdout == b""
