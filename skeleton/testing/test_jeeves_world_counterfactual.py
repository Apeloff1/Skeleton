"""Original-world counterfactual proof, approval, custody and CLI regression."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.counterfactual import (
    CounterfactualStore, approve_review, build_report, compile_review,
    edit_review, propose_review, render_report, validate_review,
)
from skeleton.jeeves.worlds.counterfactual_cli import run
from skeleton.jeeves.worlds.session import SessionStore, apply_choice, new_session
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    source = propose(
        world_id="marsh", premise="An original courier chooses a route.",
        protagonist="Iris", region="Marsh", goal="Deliver a sealed letter.",
    )
    source["scenes"].extend([
        {"id": "ferry", "title": "The ferry", "narrative": "A quiet boat waits."},
        {"id": "retreat", "title": "Return home", "narrative": "The courier returns."},
    ])
    source["choices"] = [
        {"id": "board", "from": "opening", "to": "ferry",
         "label": "Board the ferry", "requires": [], "grants": ["ticket"]},
        {"id": "flee", "from": "opening", "to": "retreat",
         "label": "Return home", "requires": [], "grants": []},
        {"id": "abandon", "from": "ferry", "to": "retreat",
         "label": "Turn back", "requires": [], "grants": []},
        {"id": "deliver", "from": "ferry", "to": "resolution",
         "label": "Deliver letter", "requires": ["ticket"], "grants": []},
        {"id": "detour", "from": "ferry", "to": "ferry",
         "label": "Explore", "requires": [], "grants": ["map"]},
    ]
    source["endings"].append({"scene": "retreat", "label": "Courier returns"})
    prove(source)
    return source


def session(source=None):
    source = source or world()
    state = new_session(source)
    for choice in ("board", "deliver"):
        state = apply_choice(state, source, choice)
    return state


def review(source=None, state=None, **kwargs):
    source = source or world()
    state = state or session(source)
    return propose_review(
        source, state, slot="save", prompt="Compare my authored endings.",
        **kwargs,
    )


def test_replayed_alternatives_and_ending_consequences():
    source, state = world(), session()
    data = review(source, state)
    report = build_report(data, source, state)
    assert report["complete"] is True
    assert report["original"]["ending"] == "Deliver a sealed letter."
    assert [v["alternative_choice"] for v in report["variants"]] == [
        "flee", "abandon", "detour",
    ]
    assert all(v["ending_changed"] for v in report["variants"])
    assert all(v["choice_witness"] != state["choices"] for v in report["variants"])
    assert report["variants"][0]["choice_witness"] == ["flee"]
    assert report["variants"][1]["choice_witness"] == ["board", "abandon"]
    assert report["variants"][2]["choice_witness"][:2] == ["board", "detour"]
    assert report["variants"][2]["flags_added"] == ["map"]


def test_review_required_before_compile_and_explicit_approval():
    source, state = world(), session()
    data = review(source, state)
    with pytest.raises(CanonError, match="counterfactual_review_required"):
        compile_review(data, source, state)
    approved = approve_review(data, source, state, "Original author approved.")
    assert data["approved"] is False
    assert approved["approved"] is True
    assert compile_review(approved, source, state)["review_digest"] == digest(approved)


def test_edit_revokes_approval_and_is_atomic():
    source, state = world(), session()
    original = approve_review(review(source, state), source, state, "Reviewed")
    before = canonical(original)
    changed = edit_review(original, source, state, {
        "action": "set_limits",
        "value": {"max_steps": 16, "max_variants": 4},
    })
    assert changed["approved"] is False
    assert original["approved"] is True
    assert canonical(original) == before
    with pytest.raises(CanonError, match="counterfactual_unsupported_edit"):
        edit_review(original, source, state, {"action": "execute", "value": {}})
    assert canonical(original) == before


def test_session_forgery_and_source_revision_fail_closed():
    source, state = world(), session()
    data = review(source, state)
    forged = copy.deepcopy(state)
    forged["choices"][0] = "flee"
    with pytest.raises(CanonError):
        validate_review(data, source, forged)
    altered = copy.deepcopy(source)
    altered["scenes"][0]["narrative"] = "Revised original text"
    prove(altered)
    with pytest.raises(CanonError, match="counterfactual_world_lease_mismatch"):
        validate_review(data, altered, state)


def test_budgets_do_not_silently_truncate():
    source, state = world(), session()
    with pytest.raises(CanonError, match="counterfactual_step_budget"):
        review(source, state, max_steps=1)
    data = review(source, state, max_variants=1)
    with pytest.raises(CanonError, match="counterfactual_variant_budget_exhausted"):
        build_report(data, source, state)
    data = review(source, state, max_steps=2)
    with pytest.raises(CanonError, match="counterfactual_step_budget_exhausted"):
        build_report(data, source, state)


def test_invalid_fields_and_noncanonical_unicode():
    source, state = world(), session()
    data = review(source, state)
    data["unknown"] = True
    with pytest.raises(CanonError, match="invalid_fields"):
        validate_review(data, source, state)
    del data["unknown"]
    data["max_variants"] = True
    with pytest.raises(CanonError, match="counterfactual_variant_budget"):
        validate_review(data, source, state)
    data["max_variants"] = 64
    data["prompt"] = "e\u0301"
    with pytest.raises(CanonError, match="noncanonical_unicode"):
        validate_review(data, source, state)


def test_html_escapes_author_text_and_refuses_scripts():
    source, state = world(), session()
    data = review(source, state)
    data["prompt"] = "<script>alert('x')</script>"
    page = render_report(build_report(data, source, state)).decode("utf-8")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "script-src 'none'" in page
    with pytest.raises(CanonError, match="counterfactual_report_schema"):
        render_report({"schema": "wrong"})


def test_unplayed_session_does_not_invent_divergences():
    source = world()
    state = new_session(source)
    data = propose_review(source, state, slot="save", prompt="No choices yet.")
    report = build_report(data, source, state)
    assert report["variants"] == []
    assert report["original"]["choice_witness"] == []


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_durable_review_compilation_verification_and_tamper(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    sessions = SessionStore(root)
    sessions.create("marsh", "save")
    first = sessions.inspect("marsh", "save")["session_digest"]
    second = sessions.choose("marsh", "save", "board", first)
    sessions.choose("marsh", "save", "deliver", second["session_digest"])
    store = CounterfactualStore(root)
    source, state = WorldStore(root).read("marsh"), sessions.read("marsh", "save")
    draft = propose_review(source, state, slot="save", prompt="Explore endings.")
    old = store.publish("marsh", "save", draft, create=True)
    with pytest.raises(CanonError, match="counterfactual_review_required"):
        store.compile("marsh", "save", old)
    reviewed = approve_review(draft, source, state, "Reviewed")
    current = store.publish("marsh", "save", reviewed, expected_digest=old)
    with pytest.raises(CanonError, match="stale_counterfactual"):
        store.publish("marsh", "save", reviewed, expected_digest=old)
    receipt = store.compile("marsh", "save", current)
    assert store.verify("marsh", "save") == receipt
    assert (root / "marsh.save.counterfactual.playable.html").exists()
    (root / "marsh.save.counterfactual.report.html").write_text("forged")
    with pytest.raises(CanonError, match="counterfactual_artifact_mismatch"):
        store.verify("marsh", "save")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_session_advancement_invalidates_review_lease(tmp_path):
    source = world()
    root = tmp_path / "private"
    WorldStore(root).publish(source, create=True)
    sessions = SessionStore(root)
    sessions.create("marsh", "save")
    store = CounterfactualStore(root)
    state = sessions.read("marsh", "save")
    store.publish("marsh", "save",
                  propose_review(source, state, slot="save", prompt="Review"), create=True)
    sessions.choose("marsh", "save", "board", digest(state))
    with pytest.raises(CanonError, match="counterfactual_session_lease_mismatch"):
        store.read("marsh", "save")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_cli_propose_preview_approve_compile_verify(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    sessions = SessionStore(root)
    sessions.create("marsh", "save")
    first = sessions.inspect("marsh", "save")["session_digest"]
    second = sessions.choose("marsh", "save", "board", first)
    sessions.choose("marsh", "save", "deliver", second["session_digest"])
    common = ["--store", str(root)]
    assert run(common + ["propose", "--world-id", "marsh", "--slot", "save",
                         "--prompt", "Show branch outcomes."]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["review_required"] is True
    assert run(common + ["preview", "--world-id", "marsh", "--slot", "save"]) == 0
    assert len(json.loads(capsys.readouterr().out)["report"]["variants"]) == 3
    assert run(common + ["approve", "--world-id", "marsh", "--slot", "save",
                         "--expected-digest", created["review_digest"],
                         "--note", "Approved"]) == 0
    approved = json.loads(capsys.readouterr().out)
    assert run(common + ["compile", "--world-id", "marsh", "--slot", "save",
                         "--expected-digest", approved["review_digest"]]) == 0
    capsys.readouterr()
    assert run(common + ["verify", "--world-id", "marsh", "--slot", "save"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_custody_rejects_symlinked_review_leaf(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    sessions = SessionStore(root)
    sessions.create("marsh", "save")
    state = sessions.read("marsh", "save")
    store = CounterfactualStore(root)
    store.publish("marsh", "save",
                  propose_review(world(), state, slot="save", prompt="Review"),
                  create=True)
    source = root / "marsh.save.counterfactual.json"
    source.unlink()
    source.symlink_to(tmp_path / "outside.json")
    with pytest.raises((CanonError, OSError)):
        store.read("marsh", "save")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_wrong_slot_cannot_relabel_replayed_review(tmp_path):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    sessions = SessionStore(root)
    sessions.create("marsh", "save")
    sessions.create("marsh", "other")
    state = sessions.read("marsh", "save")
    data = propose_review(source, state, slot="other", prompt="Wrong slot")
    # The saves have identical state digests, but distinct custody identities.
    assert digest(sessions.read("marsh", "other")) == digest(state)
    with pytest.raises(CanonError, match="counterfactual_slot_mismatch"):
        CounterfactualStore(root).publish("marsh", "save", data, create=True)
