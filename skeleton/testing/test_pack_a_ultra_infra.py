"""Pack A ultra-infra + API admit depth tests."""

from __future__ import annotations

import threading
import time

import pytest

from skeleton.api.admit_write import (
    EmergencyReadOnlyError,
    ShedError,
    set_defaults,
)
from skeleton.api.pack_a.admit_buffers import AdmitBodyStager
from skeleton.api.pack_a.admit_depth import (
    AdmitDepthContext,
    DeepWriteAdmit,
    admit_write_deep,
    reset_default_deep_admit_for_tests,
)
from skeleton.api.pack_a.priority_table import (
    PRIORITY_TABLE,
    priority_for_path,
    route_class_for_path,
    table_size,
)
from skeleton.application.pack_a_admit_depth_audit import pack_a_admit_depth_audit_snapshot
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor
from skeleton.kernel.pack_a.buffer_arena import (
    ArenaLane,
    BodyStagingPool,
    BufferArena,
    LeaseGuard,
    classify_path,
    default_body_pool,
    reset_default_pools_for_tests,
)
from skeleton.kernel.pack_a.coalesce_depth import (
    CoalesceTimeout,
    KeyedFlightBoard,
    WaiterLimitExceeded,
    admit_coalesce_key,
    namespaced_key,
    reset_default_board_for_tests,
)
from skeleton.kernel.pack_a.metrics import default_meter, reset_default_meter_for_tests
from skeleton.kernel.pack_a.staging_matrix import STAGING_MATRIX, matrix_stats, validate_matrix_sample
from skeleton.kernel.pack_a.tiered_depth import (
    AdmitDecision,
    AdmitDecisionCache,
    ChaosCachePolicy,
    NamespacedTieredCache,
    StampedeSafeCache,
    reset_default_caches_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_pack_a():
    reset_default_pools_for_tests()
    reset_default_board_for_tests()
    reset_default_caches_for_tests()
    reset_default_meter_for_tests()
    reset_default_deep_admit_for_tests()
    set_defaults(gate=AdaptiveGate(capacity=256, refill_per_sec=128), governor=ChaosGovernor())
    yield
    reset_default_pools_for_tests()
    reset_default_board_for_tests()
    reset_default_caches_for_tests()
    reset_default_meter_for_tests()
    reset_default_deep_admit_for_tests()


def test_buffer_arena_lease_and_stats():
    arena = BufferArena(ArenaLane.INGRESS)
    lease = arena.lease(128)
    assert arena.stats().leased == 1
    arena.wrap_reclaim(lease)
    assert arena.stats().leased == 0
    assert arena.stats().histogram["small_leases"] == 1


def test_lease_guard_releases_all():
    arena = BufferArena()
    with arena.guard() as g:
        g.lease(16)
        g.lease(5000)
        assert g.outstanding == 2
    assert arena.stats().leased == 0


def test_body_staging_pool_oversize():
    pool = BodyStagingPool(max_body=1024)
    with pytest.raises(ValueError):
        pool.stage(content_length=2048)


def test_body_stager_writes_payload():
    stager = AdmitBodyStager()
    bound = stager.stage_bytes("/v1/gameforge/run", b"hello-pack-a")
    assert bound.payload == b"hello-pack-a"
    assert bound.route_class == "gameforge"


def test_coalesce_board_shares_fetch():
    board = KeyedFlightBoard()
    calls = {"n": 0}
    barrier = threading.Barrier(9)
    hold = threading.Event()

    def fetch():
        calls["n"] += 1
        hold.wait(timeout=1.0)
        return "ok"

    out = []

    def worker():
        barrier.wait(timeout=1.0)
        out.append(board.get("k", fetch))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    barrier.wait(timeout=1.0)
    time.sleep(0.05)
    hold.set()
    for t in threads:
        t.join()
    assert calls["n"] == 1
    assert out == ["ok"] * 8


def test_coalesce_waiter_limit():
    board = KeyedFlightBoard(max_waiters_per_key=1)
    hold = threading.Event()
    started = threading.Event()
    leader_joined = threading.Event()

    def fetch():
        started.set()
        hold.wait(timeout=1.0)
        return 1

    def leader():
        # Claim flight as leader; hold inside fetch so joiner sees in-flight.
        board.get("x", fetch)

    t = threading.Thread(target=leader)
    t.start()
    assert started.wait(timeout=1.0)
    # Leader is inside fetch; one joiner fills the only waiter slot.
    joiner_hold = threading.Event()
    joiner_errors = []

    def joiner():
        try:
            board.get("x", lambda: 2, timeout=1.0)
        except WaiterLimitExceeded as exc:
            joiner_errors.append(exc)
        except Exception as exc:  # noqa: BLE001
            joiner_errors.append(exc)
        finally:
            joiner_hold.set()

    # First joiner occupies the single waiter slot.
    t1 = threading.Thread(target=lambda: board.get("x", lambda: 2, timeout=1.0))
    # Use a barrier-less approach: max_waiters=1 means the first try_join after
    # leader creation consumes the slot; second joiner must raise.
    # Actually leader does not call try_join — only joiners do. So first joiner
    # succeeds in joining; second must raise.
    first = {"ok": False}

    def first_joiner():
        try:
            board.get("x", lambda: 99, timeout=1.0)
            first["ok"] = True
        except Exception:
            pass

    t_first = threading.Thread(target=first_joiner)
    t_first.start()
    time.sleep(0.05)
    with pytest.raises(WaiterLimitExceeded):
        board.get("x", lambda: 2, timeout=0.2)
    hold.set()
    t.join(timeout=1.0)
    t_first.join(timeout=1.0)


def test_namespaced_key_rejects_unknown():
    with pytest.raises(ValueError):
        namespaced_key("nope", "a")
    assert namespaced_key("admit.decision", "a").startswith("admit.decision:")


def test_stampede_safe_cache_fills_once():
    ns = NamespacedTieredCache().namespace("admit.decision")
    cache = StampedeSafeCache(ns)
    n = {"v": 0}

    def compute():
        n["v"] += 1
        return n["v"]

    assert cache.get_or_compute("k", compute) == 1
    assert cache.get_or_compute("k", compute) == 1
    assert n["v"] == 1


def test_admit_decision_cache_ttl():
    c = AdmitDecisionCache(default_ttl_s=0.05)
    c.put("forge", 1, "/v1/forge/plan", AdmitDecision.ADMITTED)
    assert c.get("forge", 1, "/v1/forge/plan") is not None
    time.sleep(0.06)
    assert c.get("forge", 1, "/v1/forge/plan") is None


def test_priority_table_nonempty():
    assert table_size() >= 400
    assert route_class_for_path("/v1/gameforge/run") == "gameforge"
    assert priority_for_path("/v1/admin/shutdown") == 0


def test_admit_write_deep_safe_method():
    result = admit_write_deep(method="GET", path="/v1/gameforge/run")
    assert result.decision is AdmitDecision.SAFE_METHOD


def test_admit_write_deep_admitted():
    result = admit_write_deep(method="POST", path="/v1/forge/plan", use_decision_cache=False)
    assert result.decision is AdmitDecision.ADMITTED
    assert result.route_class == "forge"


def test_admit_write_deep_shed():
    gate = AdaptiveGate(capacity=0, refill_per_sec=0)
    deep = DeepWriteAdmit(gate=gate)
    with pytest.raises(ShedError):
        deep.admit(AdmitDepthContext(method="POST", path="/v1/upload", use_decision_cache=False))


def test_staging_matrix_stats():
    stats = matrix_stats()
    assert stats["rows"] == len(STAGING_MATRIX)
    assert validate_matrix_sample(100) == 100


def test_audit_snapshot_lists_modules():
    snap = pack_a_admit_depth_audit_snapshot()
    assert snap["kind"] == "pack_a_admit_depth_audit"
    assert snap["priority_table_size"] == table_size()
    assert "skeleton.api.pack_a.admit_depth" in snap["modules"]


def test_meter_snapshot_shape():
    m = default_meter()
    m.admit_total.labels("forge", "admitted").inc()
    snap = m.snapshot().as_dict()
    assert "counters" in snap
    assert snap["counters"]["admit_total"] >= 1.0


def test_classify_path_examples():
    assert classify_path("/auth/login") == "auth"
    assert classify_path("/v1/swarm/fence") == "swarm"
    assert classify_path("/v1/upload/x") == "bulk"


def test_admit_coalesce_key_prefers_idempotency():
    assert admit_coalesce_key("POST", "/x", "abc") == "idem:abc"
    assert admit_coalesce_key("POST", "/x") == "POST:/x"


def test_chaos_policy_defaults_allow_cache():
    policy = ChaosCachePolicy(ChaosGovernor())
    assert policy.should_cache() is True


# Parametrized depth over priority table sample
@pytest.mark.parametrize("path,rc,pr", PRIORITY_TABLE[:40])
def test_priority_table_rows(path, rc, pr):
    assert route_class_for_path(path) == rc
    assert priority_for_path(path) == pr


@pytest.mark.parametrize("rc,sz", STAGING_MATRIX[::50])
def test_staging_matrix_sample_rows(rc, sz):
    from skeleton.kernel.pack_a.staging_matrix import expected_min_size, expected_class
    assert expected_min_size(rc, sz) >= sz
    assert expected_class(sz) in {"SMALL", "MEDIUM", "LARGE"}
