"""Operator-signed read-only source capability for the local Jeeves desktop.

The real production implementation reuses canonical signed-manifest/HMAC
custody. These deterministic source-only tests never mint a legal grant,
open an installed GGUF, or claim native/device proof. Fake tool/model
objects exist only inside patched test scopes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopConfig, DesktopBridgeHold,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_agent_mode import (
    run_agent, DesktopAgentHold,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_signed_source import (
    SignedSourceAdmission, DesktopSignedSourceHold,
    preflight_signed_source,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope
from skeleton.jeeves.agent.native_source_preflight import NativeSourcePreflight
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


def admission():
    scope = Scope(
        tenant="local", subject="owner",
        model_sha256=MODEL, tokenizer_sha256=TOKENIZER,
    )
    original = NativeSourcePreflight(
        scope=scope, manifest_sha256="a" * 64,
        issued_at=100, expires_at=9999999999,
        source_count=2,
        original_byte_hashes=(("source_a", "b" * 64), ("source_b", "c" * 64)),
    )
    return SignedSourceAdmission(
        root=Path("/trusted/sources"),
        manifest=b'{"operator":"source-approval"}',
        key=b"K" * 32,
        preflight=original,
        maximum_sources=2,
        maximum_tool_calls=2,
    )


class SignedSourceConfigurationTests(unittest.TestCase):
    def _config(self, **fields):
        base = dict(
            model_root="/approved/model", state_dir="/private/sqlite",
            tenant="local", subject="owner",
        )
        base.update(fields)
        return DesktopConfig(**base)

    def test_default_desktop_agent_carries_zero_signed_file_tools(self):
        selected = self._config()
        argv = selected.worker_args()
        self.assertNotIn("--enable-source-tool", argv)
        self.assertNotIn("--source-root", argv)
        self.assertNotIn("--signed-source-manifest", argv)
        self.assertNotIn("--max-source-tool-calls", argv)

    def test_explicit_source_tool_uses_only_operator_paths_not_secrets(self):
        selected = self._config(
            signed_source_root="/trusted/sources",
            signed_source_manifest="/private/approved.manifest",
            enable_signed_source_tool=True,
            max_signed_sources=2, max_signed_tool_calls=2,
        )
        argv = selected.worker_args()
        self.assertIn("--enable-source-tool", argv)
        self.assertEqual(argv[argv.index("--source-root") + 1], "/trusted/sources")
        self.assertEqual(argv[argv.index("--signed-source-manifest") + 1],
                         "/private/approved.manifest")
        self.assertEqual(argv[argv.index("--max-source-tool-calls") + 1], "2")
        self.assertNotIn("SKELETON_OFFLINE_OPERATOR_KEY_HEX", argv)
        self.assertNotIn("task", argv)
        self.assertNotIn("prompt", argv)

    def test_no_implicit_permissions_from_manifest_path_or_truthy_flag(self):
        invalid = (
            {"signed_source_root": "/trusted/sources"},
            {"signed_source_manifest": "/private/signed.json"},
            {"signed_source_root": "/trusted/sources",
             "signed_source_manifest": "/private/signed.json"},
            {"enable_signed_source_tool": True},
            {"enable_signed_source_tool": 1},
            {"enable_signed_source_tool": "yes"},
            {"signed_source_root": "/trusted/../foreign",
             "signed_source_manifest": "/private/signed.json",
             "enable_signed_source_tool": True},
            {"max_signed_sources": 7},
            {"max_signed_tool_calls": 4},
            {"max_signed_tool_calls": True},
        )
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(
                (DesktopBridgeHold, ValueError),
            ):
                self._config(**override)


class SignedSourcePreflightTests(unittest.TestCase):
    def test_typed_admission_contains_exact_preflight_without_private_key_receipt(self):
        selected = admission()
        self.assertEqual(selected.maximum_sources, 2)
        self.assertEqual(selected.maximum_tool_calls, 2)
        public = selected.public_metadata
        self.assertEqual(public["source_count"], 2)
        self.assertEqual(public["maximum_tool_calls"], 2)
        self.assertFalse(public["source_tool_active"])
        self.assertFalse(public["release_certified"])
        self.assertNotIn("key", public)
        self.assertNotIn("root", public)
        self.assertNotIn("source_text", public)
        self.assertNotIn("manifest_raw", public)

    def test_preflight_calls_existing_source_authority_without_loading_model(self):
        signed = admission()
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli._read_private_manifest",
                return_value=signed.manifest,
            ) as read_original,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli._environment_key",
                return_value=signed.key,
            ) as independent_key,
            mock.patch(
                "skeleton.jeeves.agent.native_source_preflight.verify_sources_before_native_start",
                return_value=signed.preflight,
            ) as preflight,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.startup.activate_checked",
            ) as native_startup,
        ):
            result = preflight_signed_source(
                root=signed.root,
                manifest_path=Path("/private/approved.manifest"),
                tenant="local", subject="owner",
                maximum_sources=2, maximum_tool_calls=2,
            )
        self.assertEqual(result.manifest, signed.manifest)
        self.assertEqual(result.key, signed.key)
        self.assertIs(result.preflight, signed.preflight)
        read_original.assert_called_once()
        independent_key.assert_called_once()
        preflight.assert_called_once()
        self.assertEqual(preflight.call_args.kwargs["tenant"], "local")
        self.assertEqual(preflight.call_args.kwargs["subject"], "owner")
        native_startup.assert_not_called()

    def test_untrusted_root_manifest_and_out_of_range_tool_count_refused(self):
        a = admission()
        for field in (
            {"root": Path("relative")},
            {"root": Path("/trusted/../other")},
            {"manifest": b""},
            {"key": b"x" * 31},
            {"maximum_sources": 1},
            {"maximum_tool_calls": 0},
            {"maximum_tool_calls": 9},
        ):
            with self.subTest(field=field), self.assertRaises(
                (DesktopSignedSourceHold, ValueError),
            ):
                SignedSourceAdmission(**{
                    "root": a.root,
                    "manifest": a.manifest,
                    "key": a.key,
                    "preflight": a.preflight,
                    "maximum_sources": a.maximum_sources,
                    "maximum_tool_calls": a.maximum_tool_calls,
                    **field,
                })


class FakeFence:
    def __init__(self):
        self.calls = 0
    def assert_live(self, worker):
        self.calls += 1


class FakeBoundSourceTool:
    def __init__(self):
        self.install_calls = 0
    def install(self, registry):
        self.install_calls += 1
        self.last_registry = registry
        return registry


class FakeActivatedSource:
    def __init__(self, worker, *, quota=2):
        self.worker = worker
        self.admission = SimpleNamespace(
            maximum_tool_calls=quota,
            preflight=SimpleNamespace(manifest_sha256="a" * 64),
        )
        self.bound_tool = FakeBoundSourceTool()
        self.checks = 0
    def assert_current(self, worker):
        if worker is not self.worker:
            raise DesktopSignedSourceHold("source-bound worker changed")
        self.checks += 1


class FakeNativeRuntime:
    created = []
    tool_calls = 2
    def __init__(self, worker, *, tools):
        self.worker = worker
        self.tools = tools
        self.identity = ActiveModel.from_supervisor(worker)
        self.provider = SimpleNamespace(name="jeeves_native")
        self.created.append(self)
    def run(self, inputs):
        self.inputs = inputs
        return SimpleNamespace(
            run_id=inputs.run_id, goal_id=inputs.goal.goal_id,
            success=True,
            reason=SimpleNamespace(value="complete"),
            answer="Exact original source-aware answer",
            trace_fingerprint="a"*64,
            usage=SimpleNamespace(
                tool_calls=self.tool_calls,
                model_calls=2, steps=2,
                prompt_tokens=40, completion_tokens=30,
            ),
        )


class SignedNativeAgentTests(unittest.TestCase):
    def setUp(self):
        FakeNativeRuntime.created.clear()
        FakeNativeRuntime.tool_calls = 2

    def _invoke(self, signed_source):
        worker = FakeWorker()
        fence = FakeFence()
        tool = FakeActivatedSource(worker) if signed_source else None
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
                FakeFence,
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_runtime.NativeJeevesRuntime",
                FakeNativeRuntime,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_signed_source.ActivatedSignedSource",
                FakeActivatedSource,
            ),
        ):
            result = run_agent(
                worker, fence,
                tenant="local", subject="owner",
                prompt="Inspect approved private local evidence",
                run_id="jrun_signed_test",
                maximum_steps=5, maximum_model_calls=5,
                signed_source=tool,
            )
        return worker, fence, tool, result, FakeNativeRuntime.created[-1]

    def test_signed_read_only_lookup_is_granted_only_for_one_agent_run(self):
        worker, fence, tool, result, runtime = self._invoke(True)
        self.assertEqual(tool.bound_tool.install_calls, 1)
        self.assertIs(runtime.worker, worker)
        self.assertGreaterEqual(tool.checks, 2)
        self.assertEqual(runtime.inputs.budget.max_tool_calls, 2)
        self.assertEqual(len(runtime.inputs.grants), 1)
        self.assertEqual(runtime.inputs.grants[0].max_calls, 2)
        self.assertEqual(result["usage"]["tool_calls"], 2)
        self.assertTrue(result["signed_source_tool_active"])
        self.assertEqual(result["tool_call_ceiling"], 2)
        self.assertEqual(result["signed_source_manifest_sha256"], "a" * 64)
        self.assertFalse(result["filesystem_write_authorized"])
        self.assertFalse(result["release_certified"])

    def test_without_explicit_signed_grant_any_tool_effect_fails_closed(self):
        with self.assertRaises(DesktopAgentHold):
            self._invoke(False)
        self.assertEqual(FakeNativeRuntime.created[-1].inputs.grants, ())

    def test_tool_quota_cannot_be_exceeded_by_model_plan(self):
        FakeNativeRuntime.tool_calls = 3
        with self.assertRaises(DesktopAgentHold):
            self._invoke(True)

    def test_source_revocation_after_model_run_prevents_publication(self):
        worker = FakeWorker()
        fence = FakeFence()
        signed = FakeActivatedSource(worker)
        class RevokingRuntime(FakeNativeRuntime):
            def run(self, inputs):
                signed.assert_current = mock.Mock(
                    side_effect=DesktopSignedSourceHold("revoked"),
                )
                return super().run(inputs)
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
                FakeFence,
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_runtime.NativeJeevesRuntime",
                RevokingRuntime,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_signed_source.ActivatedSignedSource",
                FakeActivatedSource,
            ),
        ):
            with self.assertRaises(DesktopSignedSourceHold):
                run_agent(
                    worker, fence, tenant="local", subject="owner",
                    prompt="Read signed source", run_id="jrun_revocation",
                    signed_source=signed,
                )


if __name__ == "__main__":
    unittest.main()
