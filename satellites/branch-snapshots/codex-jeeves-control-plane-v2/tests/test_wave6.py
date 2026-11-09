"""Tests for wave 6: consensus, event bus, session manager,
blue-green deployments, and forecaster.
"""
from __future__ import annotations

import time

import pytest

from skeleton.core.consensus import ConsensusCluster
from skeleton.data.event_bus import EventBus
from skeleton.deployment.blue_green import BlueGreenDeployer
from skeleton.intelligence.forecaster import Forecaster
from skeleton.security.session_manager import SessionManager


class TestConsensus:
    def _cluster(self, n: int = 3):
        c = ConsensusCluster()
        for i in range(n):
            c.add_node(f"node-{i}")
        return c

    def test_election_majority(self):
        c = self._cluster(3)
        c.start_election("node-0")
        c.request_vote("node-0", 1, "node-1")
        leader = c.leader()
        assert leader is not None
        assert leader.node_id == "node-0"

    def test_no_leader_without_majority(self):
        c = self._cluster(5)
        c.start_election("node-0")
        c.request_vote("node-0", 1, "node-1")
        assert c.leader() is None

    def test_stale_term_rejected(self):
        c = self._cluster(3)
        c.start_election("node-0")
        c.request_vote("node-0", 1, "node-1")
        assert not c.request_vote("node-2", 0, "node-1")

    def test_one_vote_per_term(self):
        c = self._cluster(3)
        c.start_election("node-0")
        assert c.request_vote("node-0", 1, "node-1")
        assert not c.request_vote("node-2", 1, "node-1")

    def test_step_down_on_higher_term(self):
        c = self._cluster(3)
        c.start_election("node-0")
        c.request_vote("node-0", 1, "node-1")
        assert c.step_down("node-0", seen_term=5)
        assert c.leader() is None

    def test_heartbeat_maintains_leadership(self):
        c = self._cluster(3)
        c.start_election("node-0")
        c.request_vote("node-0", 1, "node-1")
        result = c.heartbeat("node-0", 1)
        assert result["accepted"]
        assert c.check_leader_alive()


class TestEventBus:
    def test_publish_subscribe(self):
        bus = EventBus()
        received = []
        sub = bus.subscribe("alerts.critical", lambda m: received.append(m))
        bus.publish("alerts.critical", {"msg": "x"})
        bus.drain(sub)
        assert len(received) == 1

    def test_wildcard_matching(self):
        bus = EventBus()
        received = []
        sub = bus.subscribe("alerts.*", lambda m: received.append(m))
        bus.publish("alerts.critical", {})
        bus.publish("alerts.warning", {})
        bus.publish("metrics.cpu", {})
        bus.drain(sub)
        assert len(received) == 2

    def test_exact_topic_only(self):
        bus = EventBus()
        received = []
        sub = bus.subscribe("a.b", lambda m: received.append(m))
        bus.publish("a.b.c", {})
        bus.drain(sub)
        assert received == []

    def test_backpressure_drops(self):
        bus = EventBus(queue_capacity=2)
        sub = bus.subscribe("*", lambda m: None)
        for _ in range(5):
            bus.publish("t", {})
        assert sub.dropped == 3

    def test_replay(self):
        bus = EventBus()
        sub = bus.subscribe("t.*", lambda m: None)
        bus.publish("t.a", {})
        sub2 = bus.subscribe("t.*", lambda m: None)
        count = bus.replay("t.*")
        assert count == 1
        assert len(sub2.queue) == 1


class TestSessionManager:
    def test_issue_and_validate(self):
        sm = SessionManager()
        s = sm.issue("alice", scopes=["read"])
        info = sm.validate(s.token)
        assert info["actor"] == "alice"

    def test_invalid_token(self):
        sm = SessionManager()
        assert sm.validate("nope") is None

    def test_revoke(self):
        sm = SessionManager()
        s = sm.issue("bob")
        assert sm.revoke(s.token)
        assert sm.validate(s.token) is None

    def test_rotation(self):
        sm = SessionManager()
        s1 = sm.issue("carol")
        s2 = sm.rotate(s1.token)
        assert s2 is not None
        assert sm.validate(s1.token) is None
        assert sm.validate(s2.token) is not None

    def test_concurrent_limit(self):
        sm = SessionManager(max_sessions_per_actor=2)
        sm.issue("dave")
        sm.issue("dave")
        s3 = sm.issue("dave")
        assert sm.card()["by_actor"]["dave"] == 2

    def test_revoke_all(self):
        sm = SessionManager()
        sm.issue("erin")
        sm.issue("erin")
        assert sm.revoke_all("erin") == 2


class TestBlueGreen:
    def test_full_cycle(self):
        bg = BlueGreenDeployer()
        bg.deploy("2.0")
        result = bg.smoke_test([lambda: True, lambda: True])
        assert result["healthy"]
        promoted = bg.promote()
        assert promoted["promoted"]
        assert bg.live().name == "green"

    def test_promote_blocked_on_failed_smoke(self):
        bg = BlueGreenDeployer()
        bg.deploy("2.0")
        bg.smoke_test([lambda: False])
        result = bg.promote()
        assert not result["promoted"]

    def test_rollback(self):
        bg = BlueGreenDeployer()
        bg.deploy("1.0")
        bg.smoke_test([lambda: True])
        bg.promote()
        bg.deploy("2.0")
        bg.smoke_test([lambda: True])
        bg.promote()
        result = bg.rollback()
        assert result["rolled_back"]
        assert bg.live().version == "1.0"

    def test_rollback_without_history(self):
        bg = BlueGreenDeployer()
        assert not bg.rollback()["rolled_back"]


class TestForecaster:
    def test_forecast_trend(self):
        f = Forecaster()
        for i in range(20):
            f.feed("queue", float(i))
        result = f.forecast("queue", steps=5)
        assert result["forecast"][-1]["value"] > result["forecast"][0]["value"]

    def test_time_to_threshold(self):
        f = Forecaster()
        for i in range(20):
            f.feed("disk", 50.0 + i)
        result = f.time_to_threshold("disk", 100.0)
        assert result["crosses"]
        assert result["steps"] > 0

    def test_no_crossing_flat_series(self):
        f = Forecaster()
        for _ in range(20):
            f.feed("flat", 10.0)
        result = f.time_to_threshold("flat", 100.0)
        assert not result["crosses"]

    def test_insufficient_data(self):
        f = Forecaster()
        f.feed("x", 1.0)
        assert "error" in f.forecast("x")

    def test_confidence_bands_widen(self):
        f = Forecaster()
        for i in range(30):
            f.feed("m", 100.0 + (i % 5))
        result = f.forecast("m", steps=5)
        widths = [p["upper"] - p["lower"] for p in result["forecast"]]
        assert widths[-1] > widths[0]
