"""TD (Jenkins) cross-tenant PoC against the realtime hub (S1-1 from #4128 review)."""
from skeleton.realtime.hub import RealtimeHub, sealed_principal_authorizer


def _hub():
    try:
        return RealtimeHub(authorizer=sealed_principal_authorizer)
    except TypeError:
        h = RealtimeHub()
        h.authorizer = sealed_principal_authorizer
        return h


def _types(sub):
    return [getattr(f, "event", None) or f for f in sub.drain()]


def _seen(sub, marker):
    return any(marker in repr(f) for f in sub.drain())


def test_live_other_tenant_build_event_not_delivered():
    hub = _hub()
    mallory = hub.subscribe(["build"], principal="mallory")
    hub.publish("build", "build.progress", {"m": "ALICE_SECRET_LIVE"}, job_id="j1", owner="alice", tenant="t-alice")
    assert not _seen(mallory, "ALICE_SECRET_LIVE")


def test_replay_other_tenant_build_event_not_delivered():
    hub = _hub()
    hub.publish("build", "build.progress", {"m": "ALICE_SECRET_REPLAY"}, job_id="j1", owner="alice", tenant="t-alice")
    mallory = hub.subscribe(["build"], principal="mallory", cursor=0)
    assert not _seen(mallory, "ALICE_SECRET_REPLAY")


def test_unowned_event_denied_by_default():
    hub = _hub()
    mallory = hub.subscribe(["build"], principal="mallory", cursor=0)
    hub.publish("build", "build.progress", {"m": "UNOWNED"}, job_id="j2")
    assert not _seen(mallory, "UNOWNED")


def test_job_id_without_grant_denied():
    hub = _hub()
    mallory = hub.subscribe(["build"], principal="mallory", job_id="j1")
    hub.publish("build", "build.progress", {"m": "JOB_NOGRANT"}, job_id="j1", owner="alice", tenant="t-alice")
    assert not _seen(mallory, "JOB_NOGRANT")


def test_same_principal_other_tenant_denied_without_grant():
    hub = _hub()
    alice = hub.subscribe(["build"], principal="alice")
    hub.publish("build", "build.progress", {"m": "T2_EVENT"}, job_id="j3", owner="alice", tenant="t-other")
    assert not _seen(alice, "T2_EVENT")


def test_owner_still_receives_own_untenanted_event():
    hub = _hub()
    alice = hub.subscribe(["build"], principal="alice")
    hub.publish("build", "build.progress", {"m": "MINE"}, job_id="j4", owner="alice")
    assert _seen(alice, "MINE")
