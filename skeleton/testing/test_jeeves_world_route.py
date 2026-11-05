"""Deterministic route search, operator review, replay and custody regression."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.route import (
    RouteStore, approve_spec, compile_route, propose_spec, render_guide,
    replay, solve, validate_spec,
)
from skeleton.jeeves.worlds.route_cli import run
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    source = propose(
        world_id="lantern", premise="A courier crosses the marsh.",
        protagonist="Iris", region="Lantern Marsh",
        goal="Deliver the sealed message.",
    )
    source["scenes"].insert(1, {
        "id": "ferry", "title": "Old Ferry", "narrative": "The ferry keeper waits.",
    })
    source["scenes"].insert(2, {
        "id": "bridge", "title": "Broken Bridge", "narrative": "A rope spans the gap.",
    })
    source["choices"] = [
        {"id": "a_ferry", "from": "opening", "to": "ferry",
         "label": "Take the ferry", "requires": [], "grants": ["ticket"]},
        {"id": "b_bridge", "from": "opening", "to": "bridge",
         "label": "Cross the bridge", "requires": [], "grants": ["rope"]},
        {"id": "c_deliver", "from": "ferry", "to": "resolution",
         "label": "Deliver", "requires": ["ticket"], "grants": []},
        {"id": "d_deliver", "from": "bridge", "to": "resolution",
         "label": "Deliver", "requires": ["rope"], "grants": []},
    ]
    prove(source)
    return source


def spec(**overrides):
    return propose_spec(world(), ending="resolution", **overrides)


def test_prompt_to_route_to_independent_replay():
    source = world()
    route = spec()
    assert solve(route, source) == ("a_ferry", "c_deliver")
    assert replay(route, source, solve(route, source))["ending"] == "resolution"
    assert route["approved"] is False
    with pytest.raises(CanonError, match="route_review_required"):
        compile_route(route, source)
    reviewed = approve_spec(route, source, "Reviewed by the original author.")
    handoff = compile_route(reviewed, source)
    assert handoff["choice_trace"] == ["a_ferry", "c_deliver"]
    assert handoff["operator_approved"] is True
    assert handoff["steps"][-1]["flags"] == ["ticket"]


def test_required_flags_force_alternate_path():
    route = spec(requires_flags=["rope"])
    assert solve(route, world()) == ("b_bridge", "d_deliver")
    assert replay(route, world(), ["b_bridge", "d_deliver"])["ending"] == "resolution"


def test_forbidden_choices_force_alternate_path():
    route = spec(forbids_choices=["a_ferry"])
    assert solve(route, world()) == ("b_bridge", "d_deliver")


def test_forbidden_flags_prevent_unsafe_path():
    route = spec(forbids_flags=["ticket"])
    assert solve(route, world()) == ("b_bridge", "d_deliver")
    with pytest.raises(CanonError, match="route_forbidden_transition"):
        replay(route, world(), ["a_ferry", "c_deliver"])


def test_exhausted_search_is_not_claimed_unreachable():
    route = spec(max_steps=1)
    with pytest.raises(CanonError, match="route_search_inconclusive"):
        solve(route, world())


def test_provably_unreachable_review_is_denied():
    route = spec(forbids_choices=["c_deliver", "d_deliver"])
    with pytest.raises(CanonError, match="route_unreachable"):
        solve(route, world())
    with pytest.raises(CanonError, match="route_unreachable"):
        approve_spec(route, world(), "Cannot approve without a route.")


def test_wrong_source_digest_is_refused():
    route = spec()
    route["world_digest"] = "0" * 64
    with pytest.raises(CanonError, match="route_world_lease_mismatch"):
        validate_spec(route, world())


def test_malformed_route_policy_fails_closed():
    route = spec()
    route["approved"] = 1
    with pytest.raises(CanonError, match="invalid_route_approval"):
        validate_spec(route, world())
    route = spec()
    route["requires_flags"] = ["ticket", "ticket"]
    with pytest.raises(CanonError, match="noncanonical_route_ids"):
        validate_spec(route, world())
    route = spec()
    route["max_steps"] = True
    with pytest.raises(CanonError, match="invalid_route_budget"):
        validate_spec(route, world())


def test_route_cannot_escape_terminal_ending():
    route = spec()
    with pytest.raises(CanonError, match="route_invalid_transition"):
        replay(route, world(), ["a_ferry", "c_deliver", "b_bridge"])


def test_route_does_not_accept_unearned_flags():
    route = spec(requires_flags=["ticket"])
    with pytest.raises(CanonError, match="route_witness_incomplete"):
        replay(route, world(), ["b_bridge", "d_deliver"])


def test_route_proposal_is_pure_and_deterministic():
    source = world()
    before = canonical(source)
    a = propose_spec(source, ending="resolution")
    b = propose_spec(copy.deepcopy(source), ending="resolution")
    assert canonical(a) == canonical(b)
    assert canonical(source) == before


def test_route_html_escapes_untrusted_titles():
    source = world()
    source["scenes"][1]["title"] = "<img src=x onerror=alert(1)>"
    route = approve_spec(propose_spec(source, ending="resolution"),
                         source, "Reviewed")
    handoff = compile_route(route, source)
    guide = render_guide(handoff).decode()
    assert "<img src=x" not in guide
    assert "&lt;img src=x" in guide
    assert "script-src 'none'" in guide


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_source_publish_approval_compile_verify(tmp_path):
    root = tmp_path / "private"
    world_store = WorldStore(root)
    source = world()
    world_store.publish(source, create=True)
    store = RouteStore(root)
    draft = spec()
    first = store.publish("lantern", draft, create=True)
    assert first == digest(store.read("lantern"))
    with pytest.raises(CanonError, match="route_review_required"):
        store.compile("lantern", first)
    reviewed = approve_spec(draft, source, "Operator reviewed all transitions.")
    second = store.publish("lantern", reviewed, expected_digest=first)
    receipt = store.compile("lantern", second)
    assert store.verify("lantern") == receipt
    assert (root / "lantern.route.playable.html").is_file()
    assert (root / "lantern.route.guide.html").is_file()
    assert (root / "lantern.route.witness.json").is_file()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_stale_approval_and_world_revisions_fail_closed(tmp_path):
    root = tmp_path / "private"
    source = world()
    worlds = WorldStore(root)
    old = worlds.publish(source, create=True)
    store = RouteStore(root)
    draft = spec()
    first = store.publish("lantern", draft, create=True)
    reviewed = approve_spec(draft, source, "Approved")
    with pytest.raises(CanonError, match="stale_route"):
        store.publish("lantern", reviewed, expected_digest="0" * 64)
    second = store.publish("lantern", reviewed, expected_digest=first)
    store.compile("lantern", second)
    updated = copy.deepcopy(source)
    updated["scenes"][0]["title"] = "Revised"
    worlds.publish(updated, expected_digest=old)
    with pytest.raises(CanonError, match="route_world_lease_mismatch"):
        store.verify("lantern")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_artifact_tampering_is_detected(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = RouteStore(root)
    reviewed = approve_spec(spec(), world(), "Approved")
    lease = store.publish("lantern", reviewed, create=True)
    store.compile("lantern", lease)
    (root / "lantern.route.guide.html").write_text("tampered")
    with pytest.raises(CanonError, match="route_artifact_mismatch"):
        store.verify("lantern")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_symlinked_source_and_lock_fail_closed(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    outside = tmp_path / "outside"
    outside.write_text(json.dumps(spec()))
    (root / "lantern.route.json").symlink_to(outside)
    with pytest.raises((CanonError, OSError)):
        RouteStore(root).read("lantern")
    (root / "lantern.route.json").unlink()
    (root / "lantern.lock").write_text("held")
    with pytest.raises(CanonError, match="lease_busy"):
        RouteStore(root).publish("lantern", spec(), create=True)
    assert outside.is_file()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_cli_end_to_end_reviewed_route(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + ["propose", "--world-id", "lantern",
                       "--ending", "resolution", "--require-flag", "rope"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["review_required"] is True
    assert run(args + ["approve", "--world-id", "lantern",
                       "--expected-digest", first["route_digest"],
                       "--note", "Reviewed original route."]) == 0
    second = json.loads(capsys.readouterr().out)
    assert run(args + ["compile", "--world-id", "lantern",
                       "--expected-digest", second["route_digest"]]) == 0
    receipt = json.loads(capsys.readouterr().out)["receipt"]
    assert receipt["world_id"] == "lantern"
    assert run(args + ["verify", "--world-id", "lantern"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"] == receipt

def test_large_compiled_artifact_reader_is_bounded_separately_from_source(tmp_path):
    from skeleton.jeeves.worlds.bundle import _artifact_read
    import os
    name = "large.route.playable.html"
    payload = b"x" * 600000
    (tmp_path / name).write_bytes(payload)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert _artifact_read(fd, name) == payload
    finally:
        os.close(fd)
