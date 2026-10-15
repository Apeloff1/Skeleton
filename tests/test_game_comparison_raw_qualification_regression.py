"""Regression: raw multiport emulator qualification has no policy-action tape.

Uses fake worker receipts to prove the exact native-host call budget, not to
claim a real emulator or gameplay qualification has occurred.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from skeleton.jeeves.game_comparison_schema import digest
from skeleton.jeeves.game_emulator_qualification import run_emulator_qualification


def neutral():
    return {"buttons":0,"axes":[0,0,0,0],"keys":[],
            "mouse":[0,0,0,0,0,0],"pointer":[0,0,0]}


class RawMultiportQualificationRegression(unittest.TestCase):
    def test_controller_only_tape_sets_native_step_bound(self):
        source=[ [neutral(),neutral()], [neutral(),neutral()] ]
        with patch("skeleton.jeeves.game_emulator_host.create_emulator_environment") as create, patch(
            "skeleton.jeeves.game_emulator_qualification.compare_emulator_replays"
        ) as audit:
            env=MagicMock()
            env.capture_controller_trace.return_value={
                "trace_digest":digest(["synthetic_native_trace"]),
                "source_lineage":{"capture_nonce":"test-only-nonce"},
                "steps":2,
                "transitions":[
                    {"info":{
                        "native_runs":2,
                        "frame_sha256":digest(["frame"]),
                        "audio_sha256":digest(["pcm"]),
                    }},
                ],
            }
            create.return_value.__enter__.return_value=env
            audit.return_value={
                "schema_version":"synthetic-audit-fixture-only",
                "status":"self_reported_native_replay_consistent",
                "audit_digest":digest(["fake-mirror"]),
            }
            result=run_emulator_qualification(
                "nes",core_id="fceumm",
                expected_registry_digest=digest(["fake-approved-registry"]),
                controller_tape=source,rom_source=b"synthetic-only",
                filename="synthetic.nes",runs=2,
                frames_per_step=1,
                controller_devices=["joypad","joypad"],
            )
            self.assertEqual(create.call_count,2)
            for call in create.call_args_list:
                self.assertEqual(call.kwargs["max_steps"],2)
            self.assertEqual(env.capture_controller_trace.call_count,2)
            self.assertEqual(result["controller_input_mode"],"multi_port_raw")
            self.assertEqual(result["runs_completed"],2)


if __name__=="__main__":
    unittest.main()
