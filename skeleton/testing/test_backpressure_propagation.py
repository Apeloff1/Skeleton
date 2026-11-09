from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from skeleton.kernel.backpressure import (
    AdmissionAction,
    BackpressureError,
    BackpressurePropagationController,
    BackpressureTopology,
    PressureEdge,
    PressureLevel,
    PressureObservation,
    PropagationNodePolicy,
    WorkClass,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def topology() -> BackpressureTopology:
    return BackpressureTopology(
        nodes=(
            PropagationNodePolicy("api"),
            PropagationNodePolicy("orchestrator"),
            PropagationNodePolicy("provider"),
            PropagationNodePolicy("telemetry"),
        ),
        edges=(
            PressureEdge("api", "orchestrator"),
            PressureEdge("orchestrator", "provider"),
        ),
    )


def observation(
    node: str,
    generation: int,
    load: float,
    *,
    retry_after_ms: int = 250,
    ttl_ticks: int = 8,
) -> PressureObservation:
    return PressureObservation(
        node=node,
        generation=generation,
        queue_depth=int(load * 100),
        queue_capacity=100,
        service_utilization=load,
        cause_digest=digest(f"{node}:{generation}:{load}"),
        retry_after_ms=retry_after_ms,
        ttl_ticks=ttl_ticks,
    )


class BackpressurePropagationTests(unittest.TestCase):
    def test_topology_rejects_cycles(self) -> None:
        with self.assertRaisesRegex(BackpressureError, "acyclic"):
            BackpressureTopology(
                nodes=(
                    PropagationNodePolicy("a"),
                    PropagationNodePolicy("b"),
                ),
                edges=(
                    PressureEdge("a", "b"),
                    PressureEdge("b", "a"),
                ),
            )

    def test_downstream_hard_pressure_propagates_upstream(self) -> None:
        controller = BackpressurePropagationController(topology())
        controller.observe(observation("provider", 1, 0.90))
        self.assertEqual(
            controller.signal("provider").level,
            PressureLevel.HARD,
        )
        self.assertEqual(
            controller.signal("orchestrator").level,
            PressureLevel.HARD,
        )
        api = controller.signal("api")
        self.assertEqual(api.level, PressureLevel.HARD)
        self.assertEqual(
            api.path,
            ("api", "orchestrator", "provider"),
        )
        self.assertEqual(api.source_node, "provider")
        self.assertEqual(
            controller.signal("telemetry").level,
            PressureLevel.NORMAL,
        )

    def test_generation_replay_is_identity_bound_and_stale_rejected(self) -> None:
        controller = BackpressurePropagationController(topology())
        first = observation("provider", 2, 0.80)
        controller.observe(first)
        self.assertEqual(
            controller.observe(first),
            controller.signal("provider"),
        )
        with self.assertRaisesRegex(BackpressureError, "changed identity"):
            controller.observe(
                observation("provider", 2, 0.90)
            )
        with self.assertRaisesRegex(BackpressureError, "stale"):
            controller.observe(
                observation("provider", 1, 0.80)
            )

    def test_expiry_clears_propagated_pressure(self) -> None:
        controller = BackpressurePropagationController(topology())
        controller.observe(
            observation("provider", 1, 0.99, ttl_ticks=2)
        )
        self.assertEqual(
            controller.signal("api").level,
            PressureLevel.SHED,
        )
        controller.advance(2)
        self.assertEqual(
            controller.signal("api").level,
            PressureLevel.NORMAL,
        )

    def test_hysteresis_deescalates_one_level_until_clear(self) -> None:
        controller = BackpressurePropagationController(topology())
        controller.observe(observation("provider", 1, 0.90))
        self.assertEqual(
            controller.signal("provider").level,
            PressureLevel.HARD,
        )
        controller.observe(observation("provider", 2, 0.60))
        self.assertEqual(
            controller.signal("provider").level,
            PressureLevel.SOFT,
        )
        controller.observe(observation("provider", 3, 0.20))
        self.assertEqual(
            controller.signal("provider").level,
            PressureLevel.NORMAL,
        )

    def test_soft_pressure_throttles_background_not_interactive(self) -> None:
        controller = BackpressurePropagationController(topology())
        controller.observe(observation("provider", 1, 0.75))
        self.assertEqual(
            controller.decision(
                "api", WorkClass.INTERACTIVE
            ).action,
            AdmissionAction.ACCEPT,
        )
        background = controller.decision(
            "api", WorkClass.BACKGROUND
        )
        self.assertEqual(
            background.action,
            AdmissionAction.THROTTLE,
        )
        self.assertGreater(background.retry_after_ms, 0)
        self.assertEqual(
            background.causal_path,
            ("api", "orchestrator", "provider"),
        )

    def test_hard_pressure_preserves_control_and_rejects_background(self) -> None:
        controller = BackpressurePropagationController(topology())
        controller.observe(observation("provider", 1, 0.90))
        self.assertEqual(
            controller.decision(
                "api", WorkClass.CONTROL
            ).action,
            AdmissionAction.ACCEPT,
        )
        self.assertEqual(
            controller.decision(
                "api", WorkClass.BACKGROUND
            ).action,
            AdmissionAction.REJECT,
        )
        self.assertEqual(
            controller.decision(
                "api",
                WorkClass.INTERACTIVE,
                priority=1,
            ).action,
            AdmissionAction.THROTTLE,
        )

    def test_shed_pressure_rejects_non_control(self) -> None:
        controller = BackpressurePropagationController(topology())
        controller.observe(observation("provider", 1, 0.99))
        self.assertEqual(
            controller.decision(
                "api",
                WorkClass.CONTROL,
                priority=0,
            ).action,
            AdmissionAction.THROTTLE,
        )
        self.assertEqual(
            controller.decision(
                "api",
                WorkClass.INTERACTIVE,
                priority=0,
            ).action,
            AdmissionAction.REJECT,
        )

    def test_strongest_retry_after_wins_across_dependencies(self) -> None:
        graph = BackpressureTopology(
            nodes=(
                PropagationNodePolicy("api"),
                PropagationNodePolicy("a"),
                PropagationNodePolicy("b"),
            ),
            edges=(
                PressureEdge("api", "a"),
                PressureEdge("api", "b"),
            ),
        )
        controller = BackpressurePropagationController(graph)
        controller.observe(
            observation("a", 1, 0.90, retry_after_ms=100)
        )
        controller.observe(
            observation("b", 1, 0.90, retry_after_ms=900)
        )
        signal = controller.signal("api")
        self.assertEqual(signal.retry_after_ms, 900)
        self.assertEqual(signal.source_node, "b")

    def test_report_never_self_attests_completion(self) -> None:
        controller = BackpressurePropagationController(topology())
        report = controller.report_propagation()
        self.assertEqual(report["gap"], "G022")
        self.assertFalse(report["completion_checkbox"])
        self.assertFalse(report["verification_signature"])

    def test_canonical_and_governed_ai_files_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        canonical = root / "skeleton/kernel/backpressure.py"
        mirror = root / "skeleton/ai/runtime/kernel/backpressure.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
