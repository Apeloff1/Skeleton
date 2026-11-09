from __future__ import annotations

import unittest

from skeleton.automation.agents.scheduler import SwarmScheduler, TaskState
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourcePolicy,
    GlobalResourceScheduler,
    PlanePolicy,
    ResourceRequest,
    ResourceVector,
)


def resources(cpu: int) -> ResourceVector:
    return ResourceVector(cpu_millis=cpu)


def global_scheduler() -> GlobalResourceScheduler:
    return GlobalResourceScheduler(
        GlobalResourcePolicy(
            total=resources(10),
            planes=(
                PlanePolicy(
                    "automation",
                    weight=1,
                    reserved=resources(2),
                    max_fraction=1.0,
                ),
                PlanePolicy(
                    "control",
                    weight=4,
                    reserved=resources(2),
                    max_fraction=1.0,
                ),
            ),
            aging_interval=2,
        )
    )


class GlobalResourceSwarmIntegrationTests(unittest.TestCase):
    def test_swarm_attempt_waits_for_global_capacity_then_releases_it(self) -> None:
        global_resources = global_scheduler()
        global_resources.submit(
            ResourceRequest(
                request_id="blocker",
                plane="control",
                tenant_id="system",
                resources=resources(10),
                priority=0,
                preemptible=False,
            )
        )
        blocker = global_resources.admit_next()
        self.assertIsNotNone(blocker)
        assert blocker is not None

        ran: list[str] = []
        swarm = SwarmScheduler(
            global_resources=global_resources,
            resource_plane="automation",
            resource_tenant_id="tenant-a",
            default_resources=resources(5),
            backoff_base=0,
            backoff_cap=0,
        )
        task = swarm.submit(
            "work",
            "reason",
            {},
            lambda payload: ran.append("ran") or {"ok": True},
            priority=5,
        )
        self.assertIsNone(swarm.run_once())
        self.assertEqual(task.state, TaskState.QUEUED)
        self.assertEqual(ran, [])

        global_resources.release(blocker.grant_id)
        completed = swarm.run_once()
        self.assertIs(completed, task)
        self.assertEqual(task.state, TaskState.SUCCEEDED)
        self.assertEqual(ran, ["ran"])
        self.assertEqual(
            global_resources.usage("automation").cpu_millis,
            0,
        )

    def test_failed_attempt_releases_capacity_before_retry(self) -> None:
        global_resources = global_scheduler()
        attempts = 0

        def run(payload):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("retry")
            return {"ok": True}

        swarm = SwarmScheduler(
            global_resources=global_resources,
            resource_plane="automation",
            default_resources=resources(6),
            backoff_base=0,
            backoff_cap=0,
        )
        task = swarm.submit(
            "retrying",
            "reason",
            {},
            run,
            max_retries=1,
        )
        first = swarm.run_once()
        self.assertIs(first, task)
        self.assertEqual(task.state, TaskState.QUEUED)
        self.assertEqual(
            global_resources.usage("automation").cpu_millis,
            0,
        )

        second = swarm.run_once()
        self.assertIs(second, task)
        self.assertEqual(task.state, TaskState.SUCCEEDED)
        self.assertEqual(attempts, 2)
        self.assertEqual(
            global_resources.usage("automation").cpu_millis,
            0,
        )

    def test_cancelled_local_task_cancels_pending_global_request(self) -> None:
        global_resources = global_scheduler()
        global_resources.submit(
            ResourceRequest(
                request_id="blocker",
                plane="control",
                tenant_id="system",
                resources=resources(10),
                priority=0,
                preemptible=False,
            )
        )
        blocker = global_resources.admit_next()
        self.assertIsNotNone(blocker)

        swarm = SwarmScheduler(
            global_resources=global_resources,
            resource_plane="automation",
            default_resources=resources(5),
        )
        task = swarm.submit("work", "reason", {}, lambda payload: {"ok": True})
        self.assertIsNone(swarm.run_once())
        self.assertEqual(len(global_resources.queued()), 1)

        swarm.cancel(task.task_id)
        self.assertEqual(task.state, TaskState.CANCELLED)
        self.assertEqual(global_resources.queued(), ())

    def test_global_scheduler_requires_declared_resources(self) -> None:
        swarm = SwarmScheduler(
            global_resources=global_scheduler(),
            resource_plane="automation",
        )
        with self.assertRaisesRegex(Exception, "requires declared task resources"):
            swarm.submit("work", "reason", {}, lambda payload: {"ok": True})

    def test_dead_letter_requeue_uses_fresh_resource_epoch(self) -> None:
        global_resources = global_scheduler()
        calls = 0

        def fail_then_succeed(payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("first")
            return {"ok": True}

        swarm = SwarmScheduler(
            global_resources=global_resources,
            resource_plane="automation",
            default_resources=resources(1),
            backoff_base=0,
            backoff_cap=0,
        )
        task = swarm.submit(
            "work",
            "reason",
            {},
            fail_then_succeed,
            max_retries=0,
        )
        swarm.run_once()
        self.assertEqual(task.state, TaskState.DEAD_LETTERED)
        self.assertEqual(task.resource_epoch, 0)

        swarm.requeue_dead_letter(task.task_id)
        self.assertEqual(task.resource_epoch, 1)
        swarm.run_once()
        self.assertEqual(task.state, TaskState.SUCCEEDED)
        self.assertEqual(
            global_resources.usage("automation").cpu_millis,
            0,
        )


if __name__ == "__main__":
    unittest.main()
