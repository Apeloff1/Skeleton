from __future__ import annotations

from pathlib import Path
import unittest

from skeleton.kernel.global_resource_scheduler import (
    ACTIVE,
    COMPLETED,
    REVOKING,
    GlobalResourcePolicy,
    GlobalResourceScheduler,
    PlanePolicy,
    ResourceConflict,
    ResourcePolicyError,
    ResourceRequest,
    ResourceVector,
)


def vector(
    *,
    cpu: int = 0,
    memory: int = 0,
    gpu: int = 0,
    io: int = 0,
    provider: int = 0,
) -> ResourceVector:
    return ResourceVector(cpu, memory, gpu, io, provider)


def policy() -> GlobalResourcePolicy:
    return GlobalResourcePolicy(
        total=vector(cpu=100, memory=100, gpu=100, io=100, provider=100),
        planes=(
            PlanePolicy(
                "control",
                weight=4,
                reserved=vector(cpu=20, memory=20),
                max_fraction=0.5,
            ),
            PlanePolicy(
                "interactive",
                weight=2,
                reserved=vector(cpu=20, memory=20),
                max_fraction=0.8,
            ),
            PlanePolicy(
                "background",
                weight=1,
                reserved=vector(cpu=10, memory=10),
                max_fraction=0.9,
            ),
        ),
        aging_interval=2,
    )


def request(
    request_id: str,
    plane: str,
    *,
    cpu: int,
    priority: int = 5,
    preemptible: bool = True,
) -> ResourceRequest:
    return ResourceRequest(
        request_id=request_id,
        plane=plane,
        tenant_id="tenant",
        resources=vector(cpu=cpu),
        priority=priority,
        preemptible=preemptible,
    )


class GlobalResourceSchedulerTests(unittest.TestCase):
    def test_policy_rejects_reserve_overcommit(self) -> None:
        with self.assertRaises(ResourcePolicyError):
            GlobalResourcePolicy(
                total=vector(cpu=10),
                planes=(
                    PlanePolicy(
                        "a", 1, vector(cpu=6), 1.0
                    ),
                    PlanePolicy(
                        "b", 1, vector(cpu=6), 1.0
                    ),
                ),
            )

    def test_request_identity_is_bound(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        first = scheduler.submit(request("r1", "background", cpu=10))
        retry = scheduler.submit(request("r1", "background", cpu=10))
        self.assertEqual(first, retry)
        with self.assertRaises(ResourceConflict):
            scheduler.submit(request("r1", "background", cpu=20))

    def test_idle_reserved_capacity_is_borrowable(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(request("bg", "background", cpu=70))
        grant = scheduler.admit_next()
        self.assertIsNotNone(grant)
        assert grant is not None
        self.assertTrue(grant.borrowed)
        self.assertEqual(grant.resources.cpu_millis, 70)

    def test_queued_owner_demand_reprotects_its_reserve(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(request("bg", "background", cpu=90, priority=5))
        scheduler.submit(request("control", "control", cpu=20, priority=5))
        self.assertIsNone(scheduler.admit_request("bg"))
        first = scheduler.admit_request("control")
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.request_id, "control")
        self.assertIsNone(scheduler.admit_request("bg"))

    def test_same_priority_prefers_under_served_weighted_plane(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(request("bg-first", "background", cpu=20))
        bg = scheduler.admit_next()
        self.assertIsNotNone(bg)
        scheduler.submit(request("bg-second", "background", cpu=10))
        scheduler.submit(request("interactive", "interactive", cpu=10))
        chosen = scheduler.admit_next()
        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertEqual(chosen.request_id, "interactive")

    def test_aging_prevents_permanent_priority_starvation(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(request("old", "background", cpu=10, priority=5))
        scheduler.advance(10)
        scheduler.submit(request("fresh", "interactive", cpu=10, priority=1))
        chosen = scheduler.admit_next()
        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertEqual(chosen.request_id, "old")

    def test_two_phase_preemption_never_frees_capacity_before_ack(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(
            request("low", "background", cpu=90, priority=9, preemptible=True)
        )
        low = scheduler.admit_next()
        self.assertIsNotNone(low)
        assert low is not None
        scheduler.submit(
            request("urgent", "control", cpu=20, priority=0, preemptible=False)
        )
        plan = scheduler.begin_preemption("urgent")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].grant_id, low.grant_id)
        self.assertEqual(plan[0].state, REVOKING)
        self.assertIsNone(scheduler.admit_request("urgent"))

        released = scheduler.ack_preempted(low.grant_id)
        self.assertEqual(released.state, COMPLETED)
        urgent = scheduler.admit_request("urgent")
        self.assertIsNotNone(urgent)
        assert urgent is not None
        self.assertEqual(urgent.state, ACTIVE)

    def test_cancelling_preemption_target_restores_revoking_work(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(
            request("low", "background", cpu=90, priority=9, preemptible=True)
        )
        low = scheduler.admit_next()
        self.assertIsNotNone(low)
        assert low is not None
        scheduler.submit(
            request("urgent", "control", cpu=20, priority=0)
        )
        plan = scheduler.begin_preemption("urgent")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].state, REVOKING)
        self.assertEqual(
            plan[0].revoking_for_request_id,
            "urgent",
        )

        scheduler.cancel("urgent")
        active = scheduler.active_grants()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].state, ACTIVE)
        self.assertIsNone(active[0].revoking_for_request_id)
        self.assertEqual(
            scheduler.usage("background").cpu_millis,
            90,
        )

    def test_nonpreemptible_lower_priority_work_is_not_falsely_released(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(
            request("low", "background", cpu=90, priority=9, preemptible=False)
        )
        scheduler.admit_next()
        scheduler.submit(
            request("urgent", "control", cpu=20, priority=0)
        )
        self.assertEqual(scheduler.begin_preemption("urgent"), ())

    def test_plane_max_share_blocks_monopoly(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(request("bg-a", "background", cpu=80))
        grant = scheduler.admit_next()
        self.assertIsNotNone(grant)
        scheduler.submit(request("bg-b", "background", cpu=20))
        self.assertIsNone(scheduler.admit_request("bg-b"))

    def test_release_returns_global_capacity(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        scheduler.submit(request("a", "interactive", cpu=60))
        grant = scheduler.admit_next()
        self.assertIsNotNone(grant)
        assert grant is not None
        self.assertEqual(
            scheduler.usage("interactive").cpu_millis,
            60,
        )
        scheduler.release(grant.grant_id)
        self.assertEqual(
            scheduler.usage("interactive").cpu_millis,
            0,
        )

    def test_card_does_not_self_attest_completion(self) -> None:
        scheduler = GlobalResourceScheduler(policy())
        card = scheduler.snapshot()
        self.assertEqual(card["gap"], "G021")
        self.assertFalse(card["completion_checkbox"])
        self.assertFalse(card["verification_signature"])

    def test_canonical_and_governed_ai_files_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        canonical = root / "skeleton/kernel/global_resource_scheduler.py"
        mirror = root / "skeleton/ai/runtime/kernel/global_resource_scheduler.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
