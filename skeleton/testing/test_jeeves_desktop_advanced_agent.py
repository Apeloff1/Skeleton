"""Advanced native reasoning selection after complete product implementation.

These are deterministic strict-policy tests only. They do not fake a live GGUF
or use a source-only pass as evidence of actual autonomous reasoning quality.
The runtime still owns its existing model, verification and tool executors.
"""
from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_agent_profiles import (
    PROFILE_GUARDED, PROFILE_ADVANCED, NativeProfileHold, choose_profile,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_agent_mode import (
    run_agent,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_protocol import (
    DesktopProtocolHold, command, require_command,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopBridge, DesktopBridgeHold,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL


def choose(profile_name, **replacements):
    args = dict(
        name=profile_name,
        native_max_output_tokens=1024,
        maximum_steps=8,
        maximum_model_calls=8,
        maximum_wall_seconds=180,
        signed_source_available=False,
    )
    args.update(replacements)
    return choose_profile(**args)


class NativePlanningProfileTests(unittest.TestCase):
    def test_advanced_enables_real_strict_verification_replanning(self):
        shape = choose(PROFILE_ADVANCED, signed_source_available=True)
        cfg = shape.config
        self.assertEqual(shape.name, PROFILE_ADVANCED)
        self.assertEqual(cfg.maximum_plan_steps, 8)
        self.assertEqual(cfg.maximum_replans, 2)
        self.assertEqual(cfg.grounding_repairs, 1)
        self.assertTrue(cfg.enable_model_verification)
        self.assertTrue(cfg.verify_read_only_with_model)
        self.assertTrue(cfg.fail_on_unresolved)
        self.assertFalse(cfg.stage_memory_candidates)
        self.assertFalse(cfg.stage_success_episode)
        self.assertFalse(cfg.bridge_verified_evidence)
        self.assertEqual(cfg.model_temperature, 0.0)
        self.assertEqual(cfg.final_max_tokens, 1024)
        self.assertLessEqual(cfg.verifier_max_tokens, 1024)
        self.assertFalse(shape.to_public()["release_certified"])
        self.assertFalse(shape.to_public()["model_verification_executed_proved"])

    def test_guarded_profile_has_no_automatic_replans_memory_or_tools(self):
        shape = choose(PROFILE_GUARDED, signed_source_available=True)
        cfg = shape.config
        self.assertEqual(cfg.maximum_plan_steps, 4)
        self.assertEqual(cfg.maximum_replans, 0)
        self.assertEqual(cfg.grounding_repairs, 0)
        self.assertFalse(cfg.enable_model_verification)
        self.assertFalse(cfg.verify_read_only_with_model)
        self.assertFalse(shape.to_public()["tool_grants_changed_by_profile"])
        self.assertFalse(shape.to_public()["additional_provider_started"])

    def test_advanced_low_model_budget_is_held_instead_of_downgrading(self):
        for overrides in (
            {"maximum_steps": 3},
            {"maximum_model_calls": 5},
            {"maximum_steps": True},
            {"maximum_model_calls": 100},
            {"maximum_wall_seconds": 0},
            {"native_max_output_tokens": -1},
            {"name": "automatic-superuser"},
            {"signed_source_available": 1},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(NativeProfileHold):
                choose(PROFILE_ADVANCED, **overrides)

    def test_max_plan_steps_never_exceed_source_bound_model_call_budget(self):
        shape = choose(PROFILE_ADVANCED, maximum_steps=64, maximum_model_calls=6)
        self.assertEqual(shape.config.maximum_plan_steps, 32)
        self.assertEqual(shape.config.maximum_replans, 1)
        self.assertEqual(shape.config.grounding_repairs, 0)
        self.assertFalse(shape.config.verify_read_only_with_model)

    def test_small_native_output_ceiling_never_promotes_a_fabricated_context(self):
        small = choose(PROFILE_ADVANCED, native_max_output_tokens=128)
        for name in (
            "planner_max_tokens", "step_max_tokens", "verifier_max_tokens",
            "final_max_tokens",
        ):
            self.assertLessEqual(getattr(small.config, name), 128)


class FakeFence:
    def assert_live(self, worker):
        return None


class CapturingNativeRuntime:
    instances = []
    def __init__(self, worker, *, tools, config=None):
        self.worker = worker
        self.config = config
        self.tools = tools
        self.identity = ActiveModel.from_supervisor(worker)
        self.provider = SimpleNamespace(name="jeeves_native")
        self.instances.append(self)
    def run(self, inputs):
        self.inputs = inputs
        return SimpleNamespace(
            run_id=inputs.run_id,
            goal_id=inputs.goal.goal_id,
            success=True,
            answer="Source-bound reasoning test",
            reason=SimpleNamespace(value="complete"),
            trace_fingerprint="f" * 64,
            usage=SimpleNamespace(
                model_calls=4, steps=4, tool_calls=0,
                prompt_tokens=250, completion_tokens=160,
            ),
        )


class AdvancedNativeAgentContractTests(unittest.TestCase):
    def setUp(self):
        CapturingNativeRuntime.instances.clear()

    def test_advanced_mode_passes_config_to_existing_native_worker(self):
        worker = FakeWorker()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
                FakeFence,
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_runtime.NativeJeevesRuntime",
                CapturingNativeRuntime,
            ),
        ):
            output = run_agent(
                worker, FakeFence(),
                tenant="local", subject="owner",
                prompt="Plan, inspect evidence and verify before answering",
                run_id="jrun_advanced1",
                maximum_steps=8, maximum_model_calls=8,
                reasoning_profile="advanced",
            )
        self.assertEqual(len(CapturingNativeRuntime.instances), 1)
        runtime = CapturingNativeRuntime.instances[-1]
        self.assertIs(runtime.worker, worker)
        self.assertTrue(runtime.config.enable_model_verification)
        self.assertEqual(runtime.config.maximum_replans, 2)
        self.assertEqual(runtime.inputs.grants, ())
        self.assertEqual(runtime.inputs.budget.max_tool_calls, 1)
        self.assertEqual(output["reasoning_profile"], "advanced")
        self.assertTrue(output["planning_policy"]["model_verification_requested"])
        self.assertFalse(output["planning_policy"]["model_verification_executed_proved"])
        self.assertFalse(output["release_certified"])

    def test_protocol_carries_only_operator_admitted_profile(self):
        request = command(
            "agent", run_id="jrun_advanced1",
            prompt="Verify bounded local response",
            profile="advanced",
            maximum_steps=8, maximum_model_calls=8,
            maximum_wall_seconds=180,
        )
        self.assertEqual(require_command(request), request)
        for request_params in (
            {"profile": "unbounded"},
            {"profile": 1},
            {"profile": True},
            {"profile": "advanced", "max_tool_calls": 999},
        ):
            with self.subTest(request_params=request_params), self.assertRaises(
                (DesktopProtocolHold, ValueError),
            ):
                command(
                    "agent", run_id="jrun_advanced1",
                    prompt="strict source only", **request_params,
                )
        with self.assertRaises(DesktopProtocolHold):
            command(
                "durable", run_id="wrun_original", action="resume",
                prompt="original", profile="advanced",
            )

    def test_client_must_match_chosen_profile_and_preserve_zero_tool_authority(self):
        profile = choose(PROFILE_ADVANCED).to_public()
        answer = "Verified in-bounds source response"
        payload = {
            "schema": "jeeves.desktop.strict-agent.v1",
            "status": "verified",
            "run_id": "jrun_advanced1",
            "success": True, "answer": answer,
            "output_sha256": sha256(answer.encode()).hexdigest(),
            "model_sha256": MODEL,
            "device_qualified": False,
            "release_certified": False,
            "filesystem_write_authorized": False,
            "automatic_retry": False,
            "signed_source_tool_active": False,
            "signed_source_manifest_sha256": None,
            "reasoning_profile": "advanced",
            "planning_policy": profile,
            "usage": {"tool_calls": 0},
        }
        client = DesktopBridge.__new__(DesktopBridge)
        client.model_sha256 = MODEL
        client.signed_source_manifest_sha256 = None
        response = {
            "status": "verified-agent-response",
            "run_id": "jrun_advanced1",
            "session_id": "s_owner",
            "agent": payload,
        }
        client._operation_receipt(
            "agent", {"run_id": "jrun_advanced1", "profile": "advanced"},
            response, "s_owner",
        )
        for tampering in (
            {"reasoning_profile": "guarded"},
            {"planning_policy": None},
            {"planning_policy": {**profile, "tool_grants_changed_by_profile": True}},
            {"output_sha256": "f" * 64},
            {"usage": {"tool_calls": 1}},
        ):
            import copy
            invalid = copy.deepcopy(response)
            invalid["agent"].update(tampering)
            with self.subTest(tampering=tampering), self.assertRaises(DesktopBridgeHold):
                client._operation_receipt(
                    "agent", {"run_id": "jrun_advanced1", "profile": "advanced"},
                    invalid, "s_owner",
                )


if __name__ == "__main__":
    unittest.main()
