"""Source-bound canonical world authoring, replay proof and browser acceptance."""
import copy
import json
import os
from pathlib import Path

import pytest

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, compile_html, compile_manifest,
    digest, edit, propose, prove, strict_json,
)
from skeleton.jeeves.worlds.cli import run


def world():
    return propose(world_id="cinder", premise="A courier crosses the lantern marsh.",
                   protagonist="Iris", region="Lantern Marsh",
                   goal="Deliver the sealed message without opening it.")


def test_original_prompt_to_typed_proof():
    source = world()
    assert source["prompt"].startswith("A courier")
    assert prove(source).ending_witnesses == {"resolution": ("pursue_goal",)}
    assert compile_manifest(source)["proof"]["source_digest"] == digest(source)


def test_browser_is_playable_without_network_or_eval():
    html = compile_html(world())
    assert "default-src 'none'" in html
    assert "connect-src 'none'" in html
    assert "addEventListener" in html
    assert "eval(" not in html
    assert "innerHTML" not in html
    assert "pursue_goal" in html


def test_html_escapes_hostile_user_text():
    source = world()
    source["scenes"][0]["narrative"] = "</script><img src=x onerror=alert(1)>"
    html = compile_html(source)
    assert "</script><img" not in html
    assert "\\u003c/script>" in html


def test_canonical_replay_determinism():
    source = world()
    assert canonical(source) == canonical(strict_json(canonical(source)))
    assert compile_html(source) == compile_html(copy.deepcopy(source))


def test_reject_unreachable_ending():
    source = world()
    source["scenes"].append({"id": "hidden", "title": "Hidden", "narrative": "Unvisited"})
    source["endings"].append({"scene": "hidden", "label": "Lost"})
    with pytest.raises(CanonError, match="unreachable"):
        prove(source)


def test_reject_reachable_dead_end():
    source = world()
    source["choices"].clear()
    with pytest.raises(CanonError, match="reachable_dead_end"):
        prove(source)


def test_reject_duplicate_ids():
    source = world()
    source["choices"].append(copy.deepcopy(source["choices"][0]))
    with pytest.raises(CanonError, match="duplicate_choice"):
        prove(source)


def test_reject_outgoing_from_ending():
    source = world()
    source["choices"].append({"id": "loop", "from": "resolution", "to": "opening",
                              "label": "Loop", "requires": [], "grants": []})
    with pytest.raises(CanonError, match="outgoing_from_ending"):
        prove(source)


def test_reject_unsupported_edits_without_mutation():
    source = world()
    before = canonical(source)
    with pytest.raises(CanonError, match="unsupported_edit"):
        edit(source, {"action": "execute_python", "value": {}})
    assert canonical(source) == before


def test_replace_scene_pure_and_proved():
    source = world()
    changed = edit(source, {"action": "replace_scene",
                            "value": {"id": "opening", "title": "New title",
                                      "narrative": "Revised original scene."}})
    assert changed["scenes"][0]["title"] == "New title"
    assert source["scenes"][0]["title"] != "New title"
    assert prove(changed).ending_witnesses["resolution"] == ("pursue_goal",)


def test_strict_json_rejects_duplicate_keys():
    with pytest.raises(CanonError, match="duplicate_json_key"):
        strict_json(b'{"a":1,"a":2}')


def test_strict_json_rejects_nan():
    with pytest.raises(CanonError, match="nonfinite_number"):
        strict_json(b'{"a":NaN}')


def test_bounded_json():
    with pytest.raises(CanonError, match="source_too_large"):
        strict_json(b" " * 524289)


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_persist_compile_replay(tmp_path):
    store = WorldStore(tmp_path / "worlds")
    source = world()
    old = store.publish(source, create=True)
    assert old == digest(store.read("cinder"))
    receipt = store.compile("cinder", old)
    assert receipt["source_digest"] == old
    assert (tmp_path / "worlds" / "cinder.html").exists()
    changed = edit(source, {"action": "replace_scene",
                            "value": {"id": "opening", "title": "Revised",
                                      "narrative": "Changed"}})
    new = store.publish(changed, expected_digest=old)
    assert new != old
    with pytest.raises(CanonError, match="stale_source"):
        store.compile("cinder", old)
    assert store.compile("cinder", new)["source_digest"] == new


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_stale_writer_fails_closed(tmp_path):
    store = WorldStore(tmp_path / "worlds")
    source = world()
    old = store.publish(source, create=True)
    with pytest.raises(CanonError, match="stale_source"):
        store.publish(source, expected_digest="0" * 64)
    assert digest(store.read("cinder")) == old


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_existing_source_symlink_is_rejected(tmp_path):
    store = WorldStore(tmp_path / "worlds")
    outside = tmp_path / "outside"
    outside.write_text(json.dumps(world()))
    (tmp_path / "worlds" / "cinder.json").symlink_to(outside)
    with pytest.raises((CanonError, OSError)):
        store.read("cinder")
    assert outside.exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_symlink_root_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(CanonError, match="symlink_or_untrusted_root"):
        WorldStore(alias)


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_lock_contention_fails_closed(tmp_path):
    store = WorldStore(tmp_path / "worlds")
    source = world()
    (tmp_path / "worlds" / "cinder.lock").write_text("held")
    with pytest.raises(CanonError, match="lease_busy"):
        store.publish(source, create=True)


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_cli_propose_edit_compile(tmp_path, capsys):
    root = str(tmp_path / "private")
    assert run(["--store", root, "propose", "--id", "cinder",
                "--premise", "A courier crosses the marsh.",
                "--protagonist", "Iris", "--region", "Marsh",
                "--goal", "Deliver the sealed message."]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["review_required"] is True
    operation = tmp_path / "operation.json"
    operation.write_text(json.dumps({
        "action": "replace_scene",
        "value": {"id": "opening", "title": "A new beginning",
                  "narrative": "A new original paragraph."}}))
    assert run(["--store", root, "edit", "--id", "cinder",
                "--expected-digest", first["source_digest"],
                "--operation-file", str(operation)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["source_digest"] != first["source_digest"]
    assert run(["--store", root, "compile", "--id", "cinder",
                "--expected-digest", second["source_digest"]]) == 0
    compiled = json.loads(capsys.readouterr().out)
    assert compiled["html_file"] == "cinder.html"
    assert Path(root, "cinder.html").is_file()


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_cli_stale_edit_returns_nonzero(tmp_path, capsys):
    root = str(tmp_path / "private")
    assert run(["--store", root, "propose", "--id", "cinder",
                "--premise", "A courier crosses the marsh.",
                "--protagonist", "Iris", "--region", "Marsh",
                "--goal", "Deliver the sealed message."]) == 0
    capsys.readouterr()
    operation = tmp_path / "operation.json"
    operation.write_text('{"action":"unsupported","value":{}}')
    assert run(["--store", root, "edit", "--id", "cinder",
                "--expected-digest", "0" * 64,
                "--operation-file", str(operation)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "stale_source"
