"""Choice-level deterministic coverage and playable QA custody regressions."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.playtest import PlaytestStore, prove_choice_coverage
from skeleton.jeeves.worlds.playtest_cli import run
from skeleton.jeeves.worlds.session import replay_choices
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose, prove


def authored_world():
    world = propose(world_id="valley", premise="A scout reaches the valley.",
                    protagonist="Nia", region="Valley", goal="Protect the spring.")
    world["scenes"].insert(1, {"id": "bridge", "title": "Bridge",
                               "narrative": "A narrow bridge crosses the stream."})
    world["choices"] = [
        {"id": "cross", "from": "opening", "to": "bridge", "label": "Cross",
         "requires": [], "grants": ["key"]},
        {"id": "return", "from": "bridge", "to": "opening", "label": "Return",
         "requires": [], "grants": []},
        {"id": "finish", "from": "bridge", "to": "resolution", "label": "Finish",
         "requires": ["key"], "grants": []},
        {"id": "impossible", "from": "opening", "to": "bridge",
         "label": "Use a missing seal", "requires": ["seal"], "grants": []},
    ]
    prove(world)
    return world


def test_choice_coverage_reports_unreachable_individual_choice():
    world = authored_world()
    proof = prove_choice_coverage(world)
    assert proof["uncovered_choices"] == ["impossible"]
    assert proof["total_choices"] == 4
    assert proof["covered_choices"] == 3
    assert proof["complete"] is False
    assert proof["choice_witnesses"]["cross"] == ["cross"]
    assert proof["choice_witnesses"]["finish"] == ["cross", "finish"]


def test_all_witnesses_are_real_player_traces():
    world = authored_world()
    proof = prove_choice_coverage(world)
    for choice, trace in proof["choice_witnesses"].items():
        assert replay_choices(world, trace)["steps"][-1]["choice"] == choice
    assert replay_choices(world, proof["ending_witnesses"]["resolution"])["ending"]


def test_coverage_is_stable_across_input_order_and_copies():
    world = authored_world()
    baseline = prove_choice_coverage(world)
    copy_world = copy.deepcopy(world)
    copy_world["choices"].reverse()
    assert prove_choice_coverage(copy_world)["choice_witnesses"] == baseline["choice_witnesses"]
    assert prove_choice_coverage(copy.deepcopy(world)) == baseline


def test_reachable_choice_after_flag_unlock():
    world = authored_world()
    world["choices"][3]["requires"] = ["key"]
    proof = prove_choice_coverage(world)
    assert proof["complete"]
    assert proof["choice_witnesses"]["impossible"] == ["cross", "return", "impossible"]


def test_unearned_choice_does_not_get_false_witness():
    world = authored_world()
    proof = prove_choice_coverage(world)
    assert "impossible" not in proof["choice_witnesses"]


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_strict_compile_fails_closed_without_artifacts(tmp_path):
    world = authored_world()
    WorldStore(tmp_path).publish(world, create=True)
    store = PlaytestStore(str(tmp_path))
    with pytest.raises(CanonError, match="playtest_uncovered_choices"):
        store.compile("valley", expected_world_digest=digest(world))
    assert not (tmp_path / "valley.playtest.receipt.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_opt_in_partial_coverage_playable_handoff_and_verify(tmp_path):
    world = authored_world()
    WorldStore(tmp_path).publish(world, create=True)
    store = PlaytestStore(str(tmp_path))
    receipt = store.compile("valley", expected_world_digest=digest(world),
                            require_full_coverage=False)
    assert receipt["world_digest"] == digest(world)
    assert receipt["require_full_coverage"] is False
    assert store.verify("valley") == receipt
    page = (tmp_path / "valley.playtest.playable.html").read_text()
    assert "Content-Security-Policy" in page
    assert "connect-src 'none'" in page
    assert "impossible" in page


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_tamper_and_stale_source_fail_closed(tmp_path):
    world = authored_world()
    worlds = WorldStore(tmp_path)
    worlds.publish(world, create=True)
    store = PlaytestStore(str(tmp_path))
    store.compile("valley", expected_world_digest=digest(world),
                  require_full_coverage=False)
    path = tmp_path / "valley.playtest.report.json"
    path.write_text("{}")
    with pytest.raises(CanonError, match="playtest_artifact_mismatch"):
        store.verify("valley")
    revised = copy.deepcopy(world)
    revised["scenes"][0]["narrative"] = "Changed scene"
    worlds.publish(revised, expected_digest=digest(world))
    with pytest.raises(CanonError, match="playtest_stale_source"):
        store.compile("valley", expected_world_digest=digest(world),
                      require_full_coverage=False)
    with pytest.raises(CanonError, match="playtest_receipt_mismatch"):
        store.verify("valley")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_lock_and_symlinked_receipt_fail_closed(tmp_path):
    world = authored_world()
    WorldStore(tmp_path).publish(world, create=True)
    store = PlaytestStore(str(tmp_path))
    (tmp_path / "valley.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        store.compile("valley", expected_world_digest=digest(world),
                      require_full_coverage=False)
    (tmp_path / "valley.lock").unlink()
    store.compile("valley", expected_world_digest=digest(world),
                  require_full_coverage=False)
    receipt = tmp_path / "valley.playtest.receipt.json"
    receipt.unlink()
    receipt.symlink_to(tmp_path / "valley.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("valley")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_cli_preview_compile_verify(tmp_path, capsys):
    world = authored_world()
    WorldStore(tmp_path).publish(world, create=True)
    args = ["--store", str(tmp_path)]
    assert run(args + ["preview", "--world-id", "valley"]) == 0
    preview = json.loads(capsys.readouterr().out)["coverage"]
    assert preview["uncovered_choices"] == ["impossible"]
    assert run(args + ["compile", "--world-id", "valley",
                       "--expected-world-digest", digest(world)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "playtest_uncovered_choices"
    assert run(args + ["compile", "--world-id", "valley",
                       "--expected-world-digest", digest(world),
                       "--allow-uncovered"]) == 0
    capsys.readouterr()
    assert run(args + ["verify", "--world-id", "valley"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["world_id"] == "valley"
