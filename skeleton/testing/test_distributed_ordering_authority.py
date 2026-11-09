from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from skeleton.kernel.distributed_ordering import (
    DistributedOrderingError,
    LeaseConflict,
    LeaseExpired,
    OrderingConflict,
    SQLiteDistributedOrdering,
    StaleFence,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class DistributedOrderingTests(unittest.TestCase):
    def test_hybrid_clock_never_regresses_when_physical_time_moves_back(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            first = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="l1", ttl_ns=100, now_ns=1_000,
            )
            authority.current(tenant_id="t", resource_id="r", now_ns=900)
            mark = authority.clock()
            self.assertEqual(mark.physical_ns, 1_000)
            self.assertGreater(mark.logical, first.granted_time.logical)
            self.assertGreater(mark.order_index, first.granted_time.order_index)

    def test_fence_increases_after_release_and_reacquire(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            first = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="l1", ttl_ns=100, now_ns=1000,
            )
            authority.release(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="l1", expected_fence=first.fence, now_ns=1010,
            )
            second = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="b",
                lease_id="l2", ttl_ns=100, now_ns=1020,
            )
            self.assertEqual(second.fence, first.fence + 1)
            with self.assertRaises(StaleFence):
                authority.accept_effect(
                    tenant_id="t", resource_id="r", holder_id="a",
                    lease_id="l1", fence=first.fence, sequence=1,
                    effect_id="old", effect_digest=digest("old"), now_ns=1030,
                )

    def test_expiry_reacquire_fences_old_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coord.sqlite"
            first = SQLiteDistributedOrdering(path)
            second = SQLiteDistributedOrdering(path)
            a = first.acquire(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="la", ttl_ns=10, now_ns=100,
            )
            with self.assertRaises(LeaseConflict):
                second.acquire(
                    tenant_id="t", resource_id="r", holder_id="b",
                    lease_id="lb", ttl_ns=10, now_ns=105,
                )
            b = second.acquire(
                tenant_id="t", resource_id="r", holder_id="b",
                lease_id="lb", ttl_ns=10, now_ns=110,
            )
            self.assertEqual(b.fence, a.fence + 1)
            with self.assertRaises(StaleFence):
                first.accept_effect(
                    tenant_id="t", resource_id="r", holder_id="a",
                    lease_id="la", fence=a.fence, sequence=1,
                    effect_id="stale", effect_digest=digest("x"), now_ns=111,
                )
            first.close()
            second.close()

    def test_exact_acquire_retry_does_not_change_grant(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            first = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="l1", ttl_ns=100, now_ns=1000,
            )
            retry = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="l1", ttl_ns=1000, now_ns=1001,
            )
            self.assertEqual(retry, first)

    def test_renew_requires_exact_live_identity(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            grant = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="l1", ttl_ns=10, now_ns=100,
            )
            renewed = authority.renew(
                tenant_id="t", resource_id="r", holder_id="a",
                lease_id="l1", expected_fence=grant.fence,
                ttl_ns=20, now_ns=105,
            )
            self.assertEqual(renewed.fence, grant.fence)
            self.assertEqual(renewed.version, grant.version + 1)
            with self.assertRaises(LeaseExpired):
                authority.renew(
                    tenant_id="t", resource_id="r", holder_id="a",
                    lease_id="l1", expected_fence=grant.fence,
                    ttl_ns=20, now_ns=126,
                )

    def test_effects_are_exact_next_and_totally_ordered(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            a = authority.acquire(
                tenant_id="t", resource_id="a", holder_id="w",
                lease_id="la", ttl_ns=1000, now_ns=100,
            )
            b = authority.acquire(
                tenant_id="t", resource_id="b", holder_id="w",
                lease_id="lb", ttl_ns=1000, now_ns=100,
            )
            one = authority.accept_effect(
                tenant_id="t", resource_id="a", holder_id="w",
                lease_id="la", fence=a.fence, sequence=1,
                effect_id="e1", effect_digest=digest("1"), now_ns=101,
            )
            two = authority.accept_effect(
                tenant_id="t", resource_id="b", holder_id="w",
                lease_id="lb", fence=b.fence, sequence=1,
                effect_id="e2", effect_digest=digest("2"), now_ns=99,
            )
            self.assertGreater(
                two.accepted_time.order_index, one.accepted_time.order_index
            )
            self.assertEqual(
                two.accepted_time.physical_ns, one.accepted_time.physical_ns
            )
            with self.assertRaisesRegex(OrderingConflict, "exact-next"):
                authority.accept_effect(
                    tenant_id="t", resource_id="a", holder_id="w",
                    lease_id="la", fence=a.fence, sequence=3,
                    effect_id="e3", effect_digest=digest("3"), now_ns=102,
                )

    def test_effect_idempotency_is_identity_bound(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            grant = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="w",
                lease_id="l", ttl_ns=100, now_ns=100,
            )
            first = authority.accept_effect(
                tenant_id="t", resource_id="r", holder_id="w",
                lease_id="l", fence=grant.fence, sequence=1,
                effect_id="e", effect_digest=digest("same"), now_ns=101,
            )
            replay = authority.accept_effect(
                tenant_id="t", resource_id="r", holder_id="w",
                lease_id="l", fence=grant.fence, sequence=1,
                effect_id="e", effect_digest=digest("same"), now_ns=102,
            )
            self.assertEqual(replay, first)
            with self.assertRaisesRegex(OrderingConflict, "changed effect identity"):
                authority.accept_effect(
                    tenant_id="t", resource_id="r", holder_id="w",
                    lease_id="l", fence=grant.fence, sequence=1,
                    effect_id="e", effect_digest=digest("changed"), now_ns=103,
                )

    def test_tenants_have_independent_resource_leases(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            a = authority.acquire(
                tenant_id="a", resource_id="same", holder_id="w1",
                lease_id="a1", ttl_ns=10, now_ns=100,
            )
            b = authority.acquire(
                tenant_id="b", resource_id="same", holder_id="w2",
                lease_id="b1", ttl_ns=10, now_ns=100,
            )
            self.assertEqual(a.fence, 1)
            self.assertEqual(b.fence, 1)

    def test_restart_preserves_clock_fence_and_effect_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coord.sqlite"
            with SQLiteDistributedOrdering(path) as first:
                grant = first.acquire(
                    tenant_id="t", resource_id="r", holder_id="w",
                    lease_id="l1", ttl_ns=10, now_ns=100,
                )
                receipt = first.accept_effect(
                    tenant_id="t", resource_id="r", holder_id="w",
                    lease_id="l1", fence=grant.fence, sequence=1,
                    effect_id="e1", effect_digest=digest("1"), now_ns=101,
                )
            with SQLiteDistributedOrdering(path) as second:
                next_grant = second.acquire(
                    tenant_id="t", resource_id="r", holder_id="w2",
                    lease_id="l2", ttl_ns=10, now_ns=111,
                )
                self.assertEqual(next_grant.fence, grant.fence + 1)
                self.assertGreater(
                    next_grant.granted_time.order_index,
                    receipt.accepted_time.order_index,
                )
                self.assertEqual(
                    len(second.effects(tenant_id="t", resource_id="r")), 1
                )

    def test_invalid_ttl_digest_and_future_fence_fail_closed(self) -> None:
        with SQLiteDistributedOrdering() as authority:
            with self.assertRaises(DistributedOrderingError):
                authority.acquire(
                    tenant_id="t", resource_id="r", holder_id="w",
                    lease_id="l", ttl_ns=0, now_ns=100,
                )
            grant = authority.acquire(
                tenant_id="t", resource_id="r", holder_id="w",
                lease_id="l", ttl_ns=10, now_ns=100,
            )
            with self.assertRaisesRegex(DistributedOrderingError, "SHA-256"):
                authority.accept_effect(
                    tenant_id="t", resource_id="r", holder_id="w",
                    lease_id="l", fence=grant.fence, sequence=1,
                    effect_id="e", effect_digest="ABC", now_ns=101,
                )
            with self.assertRaisesRegex(LeaseConflict, "future"):
                authority.accept_effect(
                    tenant_id="t", resource_id="r", holder_id="w",
                    lease_id="l", fence=grant.fence + 1, sequence=1,
                    effect_id="e2", effect_digest=digest("x"), now_ns=101,
                )

    def test_canonical_and_governed_ai_files_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        canonical = root / "skeleton/kernel/distributed_ordering.py"
        mirror = root / "skeleton/ai/runtime/kernel/distributed_ordering.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
