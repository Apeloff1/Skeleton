"""Original lore: exclusive branches, contradiction proof, persistence and CLI."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.lore import (
    LoreStore, approve_lore, compile_lore, edit_lore, propose_lore,
    render_lore, reveal_lore, validate_lore,
)
from skeleton.jeeves.worlds.lore_cli import run
from skeleton.jeeves.worlds.session import SessionStore, apply_choice, new_session
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    source = propose(
        world_id="marsh", premise="An original courier chooses a route.",
        protagonist="Iris", region="Marsh", goal="Deliver the letter.",
    )
    source["scenes"].append({
        "id": "retreat", "title": "Return", "narrative": "The courier returns.",
    })
    source["choices"] = [
        {"id": "deliver", "from": "opening", "to": "resolution",
         "label": "Deliver", "requires": [], "grants": ["delivered"]},
        {"id": "retreat", "from": "opening", "to": "retreat",
         "label": "Return", "requires": [], "grants": ["returned"]},
    ]
    source["endings"].append({"scene": "retreat", "label": "Returned"})
    prove(source)
    return source


def facts():
    return [
        {"id": "delivered", "subject": "The courier",
         "scene": "resolution", "statement": "The letter was delivered.",
         "requires_flags": ["delivered"], "contradicts": ["returned"]},
        {"id": "returned", "subject": "The courier",
         "scene": "retreat", "statement": "The letter was returned.",
         "requires_flags": ["returned"], "contradicts": ["delivered"]},
    ]


def lore(source=None):
    source = source or world()
    data = propose_lore(
        source, prompt="Author original courier history.",
        subject="The letter", statement="A sealed letter exists.",
    )
    data["facts"].extend(facts())
    validate_lore(data, source)
    return data


def test_exclusive_branches_allow_opposing_canon_facts():
    source = world()
    data = lore(source)
    approved = approve_lore(data, source, "Original author reviewed.")
    handoff = compile_lore(approved, source)
    assert handoff["states_proven"] >= 3
    assert handoff["facts"][1]["id"] == "delivered"
    assert approved["approved"] is True
    assert data["approved"] is False


def test_contradictions_on_same_reachable_trace_fail_closed():
    source = world()
    data = lore(source)
    data["facts"][1]["scene"] = "opening"
    data["facts"][1]["requires_flags"] = []
    data["facts"][2]["scene"] = "opening"
    data["facts"][2]["requires_flags"] = []
    with pytest.raises(CanonError, match="lore_canon_contradiction"):
        validate_lore(data, source)


def test_asymmetric_and_self_contradictions_rejected():
    source = world()
    data = lore(source)
    data["facts"][2]["contradicts"] = []
    with pytest.raises(CanonError, match="lore_asymmetric_contradiction"):
        validate_lore(data, source)
    data["facts"][2]["contradicts"] = ["delivered"]
    data["facts"][1]["contradicts"] = ["delivered"]
    with pytest.raises(CanonError, match="lore_invalid_contradiction"):
        validate_lore(data, source)


def test_actual_player_reveals_only_earned_branch_lore():
    source = world()
    data = lore(source)
    state = apply_choice(new_session(source), source, "deliver")
    result = reveal_lore(data, source, state)
    assert [entry["fact_id"] for entry in result["revealed"]] == [
        "origin", "delivered",
    ]
    assert result["remaining"] == ["returned"]
    assert result["revealed"][1]["first_seen_step"] == 1
    retreat = apply_choice(new_session(source), source, "retreat")
    assert [entry["fact_id"] for entry in reveal_lore(data, source, retreat)["revealed"]] == [
        "origin", "returned",
    ]


def test_source_change_revokes_lore_lease():
    source = world()
    data = lore(source)
    changed = copy.deepcopy(source)
    changed["scenes"][0]["title"] = "Revised opening"
    prove(changed)
    with pytest.raises(CanonError, match="lore_world_lease_mismatch"):
        validate_lore(data, changed)


def test_atomic_batch_edit_and_approval_revocation():
    source = world()
    approved = approve_lore(lore(source), source, "Reviewed")
    before = canonical(approved)
    changed = edit_lore(approved, source, {
        "action": "batch", "value": [
            {"action": "replace", "value": {
                "id": "origin", "subject": "The letter", "scene": "opening",
                "statement": "A sealed original letter is entrusted to Iris.",
                "requires_flags": [], "contradicts": [],
            }},
        ],
    })
    assert changed["approved"] is False
    assert approved["approved"] is True
    assert canonical(approved) == before
    with pytest.raises(CanonError, match="lore_unsupported_edit"):
        edit_lore(approved, source, {"action": "eval", "value": {}})
    assert canonical(approved) == before


def test_unknown_scene_flag_and_duplicate_fact_fail_closed():
    source = world()
    data = lore(source)
    data["facts"][1]["scene"] = "absent"
    with pytest.raises(CanonError, match="lore_unknown_scene"):
        validate_lore(data, source)
    data = lore(source)
    data["facts"][1]["requires_flags"] = ["unearned"]
    with pytest.raises(CanonError, match="lore_unknown_flag"):
        validate_lore(data, source)
    data = lore(source)
    data["facts"].append(copy.deepcopy(data["facts"][1]))
    with pytest.raises(CanonError, match="lore_duplicate_fact"):
        validate_lore(data, source)


def test_review_required_and_escaped_static_lore_atlas():
    source = world()
    data = lore(source)
    with pytest.raises(CanonError, match="lore_review_required"):
        compile_lore(data, source)
    data["facts"][0]["statement"] = "<script>alert('bad')</script>"
    approved = approve_lore(data, source, "Reviewed")
    page = render_lore(compile_lore(approved, source)).decode("utf-8")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "script-src 'none'" in page


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_durable_publish_approve_compile_verify_and_tamper(tmp_path):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    store = LoreStore(root)
    draft = lore(source)
    old = store.publish("marsh", draft, create=True)
    with pytest.raises(CanonError, match="lore_review_required"):
        store.compile("marsh", old)
    approved = approve_lore(draft, source, "Reviewed")
    current = store.publish("marsh", approved, expected_digest=old)
    with pytest.raises(CanonError, match="stale_lore"):
        store.publish("marsh", approved, expected_digest=old)
    receipt = store.compile("marsh", current)
    assert store.verify("marsh") == receipt
    assert (root / "marsh.lore.playable.html").exists()
    (root / "marsh.lore.atlas.html").write_text("tampered")
    with pytest.raises(CanonError, match="lore_artifact_mismatch"):
        store.verify("marsh")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_lore_cli_full_operator_flow_and_real_save_reveal(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + ["propose", "--world-id", "marsh",
                       "--prompt", "Original courier history",
                       "--subject", "Letter", "--statement", "A sealed letter."]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["review_required"]
    assert run(args + ["approve", "--world-id", "marsh",
                       "--expected-digest", first["lore_digest"],
                       "--note", "Reviewed"]) == 0
    approved = json.loads(capsys.readouterr().out)
    assert run(args + ["compile", "--world-id", "marsh",
                       "--expected-digest", approved["lore_digest"]]) == 0
    capsys.readouterr()
    assert run(args + ["verify", "--world-id", "marsh"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    sessions = SessionStore(root)
    sessions.create("marsh", "save")
    first = sessions.inspect("marsh", "save")["session_digest"]
    sessions.choose("marsh", "save", "deliver", first)
    assert run(args + ["reveal", "--world-id", "marsh", "--slot", "save"]) == 0
    revealed = json.loads(capsys.readouterr().out)["reveal"]["revealed"]
    assert [entry["fact_id"] for entry in revealed] == ["origin"]


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_symlinked_lore_source_refused(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = LoreStore(root)
    store.publish("marsh", lore(), create=True)
    leaf = root / "marsh.lore.json"
    leaf.unlink()
    leaf.symlink_to(tmp_path / "outside.json")
    with pytest.raises((CanonError, OSError)):
        store.read("marsh")


def test_lore_browser_editor_escapes_authored_html():
    from skeleton.jeeves.worlds.lore_editor import render_lore_editor
    source = world()
    data = lore(source)
    data["facts"][0]["statement"] = "</script><img src=x onerror=alert(1)>"
    page = render_lore_editor(source, data).decode("utf-8")
    assert "</script><img" not in page
    assert "\\u003c/script>" in page
    assert "connect-src 'none'" in page
    assert "script-src 'sha256-" in page
    assert "role='status'" in page


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_lore_editor_cli_publish_verify_and_tamper(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = LoreStore(root)
    revision = store.publish("marsh", lore(), create=True)
    args = ["--store", str(root)]
    assert run(args + ["editor", "--world-id", "marsh",
                       "--expected-digest", revision]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["editor"]["lore_digest"] == revision
    assert run(args + ["verify-editor", "--world-id", "marsh"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    (root / "marsh.lore.editor.html").write_text("tampered")
    assert run(args + ["verify-editor", "--world-id", "marsh"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "lore_editor_artifact_mismatch"


def test_lore_is_rendered_inside_real_canonical_playable():
    import base64
    from hashlib import sha256
    import re
    from skeleton.jeeves.worlds.lore_player import render_lore_playable
    source = world()
    approved = approve_lore(lore(source), source, "Reviewed")
    page = render_lore_playable(source, approved).decode("utf-8")
    assert "const lore = model.lore;" in page
    assert "Discovered lore" in page
    assert "discovered = new Set(); render();" in page
    assert "script-src 'sha256-" in page
    assert "connect-src 'none'" in page
    assert "jeeves.world.lore_player.v1" in page
    scripts = re.findall(r"<script>(.*?)</script>", page, flags=re.DOTALL)
    assert len(scripts) == 1
    policy_hash = base64.b64encode(
        sha256(scripts[0].encode("utf-8")).digest()).decode("ascii")
    assert "sha256-" + policy_hash in page
    with pytest.raises(CanonError, match="lore_review_required"):
        render_lore_playable(source, lore(source))


def test_lore_player_does_not_inject_authored_script():
    from skeleton.jeeves.worlds.lore_player import render_lore_playable
    source = world()
    data = lore(source)
    data["facts"][0]["statement"] = "</script><img src=x onerror=alert(1)>"
    approved = approve_lore(data, source, "Reviewed")
    page = render_lore_playable(source, approved).decode("utf-8")
    assert "</script><img" not in page
    assert "\\u003c/script>" in page
