import json

import pytest

from skeleton.app_services.auth import AuthError, verify_password
from skeleton.app_services.container import AppServices
from skeleton.app_services.db import MIGRATIONS, Database
from skeleton.app_services.events import (
    EventBusBridge, FanOutPublisher, JobEventPublisher, NullJobEventPublisher, make_envelope)
from skeleton.app_services.jobs import AgentEventEmitter, SqliteJobQueue
from skeleton.app_services import ports
from skeleton.kernel.events import EventBus


class Sink:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


@pytest.fixture
def app(tmp_path):
    s = AppServices.open(tmp_path)
    yield s
    s.close()


@pytest.fixture
def owner(app):
    return app.auth.register("dev@example.com", "correct-horse-battery")


def test_migrations_idempotent_and_versioned(tmp_path):
    db = Database(tmp_path / "x.db")
    assert db.migrate() == [m[0] for m in MIGRATIONS]
    assert db.migrate() == []
    assert db.schema_version() == MIGRATIONS[-1][0]
    db2 = Database(tmp_path / "y.db")
    assert db2.migrate(target=2) == [1, 2]
    assert db2.migrate() == [3, 4]


def test_adapters_satisfy_ports(app):
    assert isinstance(app.auth, ports.SessionResolver)
    assert isinstance(app.auth.users, ports.UserRepository)
    assert isinstance(app.auth.sessions, ports.SessionRepository)
    assert isinstance(app.projects, ports.ProjectRepository)
    assert isinstance(app.builds, ports.BuildRepository)
    assert isinstance(app.queue, ports.JobQueue)
    assert isinstance(app.assets, ports.AssetStore)
    assert isinstance(app.events, JobEventPublisher)
    assert isinstance(NullJobEventPublisher(), JobEventPublisher)


def test_register_login_resolve_logout(app, owner):
    with pytest.raises(ValueError):
        app.auth.register("dev@example.com", "another-password")
    with pytest.raises(ValueError):
        app.auth.register("x@example.com", "short")
    with pytest.raises(AuthError):
        app.auth.login("dev@example.com", "wrong-password!")
    with pytest.raises(AuthError):
        app.auth.login("nobody@example.com", "whatever-pass")
    issued = app.auth.login("DEV@example.com", "correct-horse-battery", scopes=["build"])
    assert "token" not in repr(issued) or "<redacted>" in repr(issued)
    p = app.auth.resolve_session(issued.token)
    assert p.user_id == owner.user_id and p.scopes == ("build",)
    # token never persisted in plaintext
    rows = app.db.query("SELECT * FROM sessions")
    assert issued.token not in json.dumps([dict(r) for r in rows])
    assert app.auth.logout(issued.token)
    assert app.auth.resolve_session(issued.token) is None


def test_password_change_and_disable_revoke_sessions(app, owner):
    t = app.auth.login("dev@example.com", "correct-horse-battery").token
    app.auth.change_password(owner.user_id, "correct-horse-battery", "new-password-123")
    assert app.auth.resolve_session(t) is None
    t2 = app.auth.login("dev@example.com", "new-password-123").token
    app.auth.disable_user(owner.user_id)
    assert app.auth.resolve_session(t2) is None
    with pytest.raises(AuthError):
        app.auth.login("dev@example.com", "new-password-123")
    assert not verify_password("x", "garbage")


def test_session_expiry(app, owner):
    now = [1000.0]
    app.auth.clock = lambda: now[0]
    app.auth.ttl = 10
    t = app.auth.login("dev@example.com", "correct-horse-battery").token
    now[0] += 5
    assert app.auth.resolve_session(t) is not None  # sliding renew -> expires 1015
    now[0] += 11
    assert app.auth.resolve_session(t) is None
    assert app.auth.sweep() == 1


def test_projects_and_builds(app, owner):
    p = app.projects.create_project(owner.user_id, "Dragon Quest", {"engine": "gb"})
    assert app.projects.list_projects(owner.user_id) == [p]
    p2 = app.projects.update_settings(p.project_id, {"engine": "nes"})
    assert p2.settings == {"engine": "nes"}
    b = app.build_service.submit(p.project_id, target="nes")
    assert b.status == "queued" and b.job_id
    with pytest.raises(ValueError):
        app.builds.set_status(b.build_id, "bogus")
    assert app.build_service.cancel(b.build_id)
    assert app.builds.get_build(b.build_id).status == "cancelled"


def test_build_runner_success_emits_envelopes(app, owner):
    sink = Sink()
    app.events.subscribe(sink)
    p = app.projects.create_project(owner.user_id, "g")
    b = app.build_service.submit(p.project_id, target="gb", correlation_id="corr-1")

    def executor(ctx):
        ctx.log("compiling api_key=abc123 now")
        ctx.progress(0.5, "half")
        return {"rom_asset": "ast_1", "token": "leak"}

    runner = app.build_runner(executor)
    assert runner.drain() == 1
    assert app.builds.get_build(b.build_id).status == "succeeded"
    types = [e["type"] for e in sink.events]
    assert types == ["build.started", "build.log", "build.progress", "build.completed"]
    ids = [e["id"] for e in sink.events]
    assert ids == sorted(ids) and len(set(ids)) == 4
    for e in sink.events:
        assert e["v"] == 1 and e["channel"] == "build" and e["job_id"] == b.job_id
        assert e["correlation_id"] == "corr-1"
    blob = json.dumps(sink.events)
    assert "abc123" not in blob and "leak" not in blob


def test_build_retry_then_dead_letter(app, owner):
    sink = Sink()
    app.events.subscribe(sink)
    p = app.projects.create_project(owner.user_id, "g")
    b = app.build_service.submit(p.project_id, max_attempts=2)
    runner = app.build_runner(lambda ctx: 1 / 0, retry_delay_s=0)
    runner.run_once()
    assert app.builds.get_build(b.build_id).status == "queued"
    runner.run_once()
    assert app.queue.get(b.job_id).status == "dead"
    assert app.builds.get_build(b.build_id).status == "failed"
    fails = [e for e in sink.events if e["type"] == "build.failed"]
    assert [f["payload"]["will_retry"] for f in fails] == [True, False]


def test_queue_lease_expiry_and_idempotency(tmp_path):
    db = Database()
    db.migrate()
    now = [0.0]
    q = SqliteJobQueue(db, clock=lambda: now[0])
    j = q.enqueue("k", {"a": 1}, idempotency_key="once")
    assert q.enqueue("k", {"a": 2}, idempotency_key="once").job_id == j.job_id
    c = q.claim("w1", lease_s=10)
    assert c.job_id == j.job_id and q.claim("w2") is None
    now[0] = 11
    c2 = q.claim("w2", lease_s=10)
    assert c2.lease_owner == "w2" and c2.attempts == 2
    assert not q.heartbeat(j.job_id, "w1")
    assert q.complete(j.job_id, "w2", {"ok": True}).status == "succeeded"
    assert q.counts() == {"succeeded": 1}


def test_fanout_isolation_and_unsubscribe():
    fan = FanOutPublisher()

    class Boom:
        def publish(self, e):
            raise RuntimeError

    good = Sink()
    fan.subscribe(Boom())
    unsub = fan.subscribe(good)
    fan.publish(make_envelope("presence", "presence.update", {"user": "u"}))
    assert len(good.events) == 1
    unsub()
    fan.publish(make_envelope("presence", "presence.update", {}))
    assert len(good.events) == 1
    with pytest.raises(ValueError):
        make_envelope("build", "agent.step")
    with pytest.raises(TypeError):
        fan.subscribe(object())


def test_bridge_to_kernel_event_bus_and_agent_emitter():
    bus = EventBus()
    seen = []
    bus.subscribe("*", seen.append)
    fan = FanOutPublisher()
    fan.subscribe(EventBusBridge(bus))
    ag = AgentEventEmitter(fan)
    ag.started("coder", correlation_id="c")
    ag.step("coder", "plan", {"password": "p"})
    ag.completed("coder")
    assert [e.topic for e in seen] == ["app.agent.started", "app.agent.step", "app.agent.completed"]
    assert seen[1].payload["payload"]["password"] == "[REDACTED]"


def test_asset_store_dedup_quota_and_traversal(app, owner):
    p = app.projects.create_project(owner.user_id, "g")
    a1 = app.assets.put(p.project_id, "sprites/hero.png", b"PNG", "image/png")
    a2 = app.assets.put(p.project_id, "sprites/hero2.png", b"PNG")
    assert a1.sha256 == a2.sha256
    assert app.assets.open_bytes(a1.asset_id) == b"PNG"
    for bad in ("../x", "/etc/passwd", "a/../b", "", "a\x00b"):
        with pytest.raises(ValueError):
            app.assets.put(p.project_id, bad, b"x")
    blob = app.assets._blob(a1.sha256)
    assert app.assets.remove(a1.asset_id) and blob.exists()
    assert app.assets.remove(a2.asset_id) and not blob.exists()
    a3 = app.assets.put(p.project_id, "m.bin", b"1")
    a4 = app.assets.put(p.project_id, "m.bin", b"22")
    assert a3.asset_id == a4.asset_id and a4.size == 2
    app.assets.quota = 3
    with pytest.raises(ValueError):
        app.assets.put(p.project_id, "big.bin", b"1234")
    assert [a.name for a in app.assets.list(p.project_id)] == ["m.bin"]
