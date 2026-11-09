from __future__ import annotations

import unittest

from skeleton.ai.planning.construction_authority import (
    ConstructionAuthorityError,
    ConstructionPacketBuilder,
    RadarState,
    TechnologyCandidate,
    TechnologyRadar,
)


class P3ConstructionAuthorityTests(unittest.TestCase):
    def test_construction_packet_is_deterministic_and_non_authoritative(self) -> None:
        builder = ConstructionPacketBuilder()
        kwargs = dict(
            packet_id="packet:p3",
            sources={
                "machine/ai_p3_execution_map.json": {"version": "0.1.0"},
                "machine/ai_p3_task_backlog.json": {"task_count": 6},
            },
            authority_refs=("authority:p3-map",),
            scope_refs=("scope:257",),
            task_refs=("task:P3-ACCEPTANCE-01",),
            evidence_refs=("evidence:acceptance-ci",),
            unresolved_refs=("unresolved:234-queued",),
            handoff_refs=("handoff:p3-engineering-stack",),
        )
        first = builder.build(**kwargs)
        second = builder.build(**kwargs)
        self.assertEqual(first.packet_digest, second.packet_digest)
        self.assertFalse(first.completion_authority)
        self.assertEqual(
            tuple(section.section_id for section in first.sections),
            builder.REQUIRED_SECTION_IDS,
        )

    def test_packet_requires_unresolved_and_handoff_evidence(self) -> None:
        with self.assertRaisesRegex(ConstructionAuthorityError, "packet_reference"):
            ConstructionPacketBuilder().build(
                packet_id="packet:p3",
                sources={"a": 1, "b": 2},
                authority_refs=("authority:a",),
                scope_refs=("scope:a",),
                task_refs=("task:a",),
                evidence_refs=("evidence:a",),
                unresolved_refs=(),
                handoff_refs=("handoff:a",),
            )

    def test_radar_adoption_requires_adr_and_two_evidence_refs(self) -> None:
        candidate = TechnologyCandidate(
            candidate_id="tech:engine",
            state=RadarState.TRIAL,
            evidence_refs=("evidence:baseline",),
            exit_criteria=("migration path remains executable",),
            review_after_cycles=4,
            vendor_dependency="vendor:x",
        )
        with self.assertRaisesRegex(ConstructionAuthorityError, "architecture decision"):
            TechnologyRadar().transition(
                candidate,
                RadarState.ADOPT,
                evidence_refs=("evidence:eval", "evidence:security"),
            )

        adopted, decision = TechnologyRadar().transition(
            candidate,
            RadarState.ADOPT,
            evidence_refs=("evidence:eval", "evidence:security"),
            architecture_decision_ref="adr:0042",
        )
        self.assertEqual(adopted.state, RadarState.ADOPT)
        self.assertEqual(decision.architecture_decision_ref, "adr:0042")
        self.assertEqual(len(decision.decision_digest), 64)

    def test_radar_blocks_permanent_or_invalid_state_jumps(self) -> None:
        candidate = TechnologyCandidate(
            candidate_id="tech:trial",
            state=RadarState.WATCH,
            evidence_refs=("evidence:scan",),
            exit_criteria=("exit if quality target missed",),
            review_after_cycles=2,
        )
        with self.assertRaisesRegex(ConstructionAuthorityError, "not allowed"):
            TechnologyRadar().transition(
                candidate,
                RadarState.ADOPT,
                evidence_refs=("evidence:a", "evidence:b"),
                architecture_decision_ref="adr:1",
            )


if __name__ == "__main__":
    unittest.main()
