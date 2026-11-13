"""Real-source preload admission contracts for the offline Jeeves desktop.

All synthetic installed models and host measurements in these tests are
deliberately source-only; no installed GGUF is activated and no hardware
qualification is claimed. The production implementation re-reads live
device/cgroup and original installed-source rights just before startup.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
    InstalledModelReport,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan import (
    CgroupObservation,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopBridge, DesktopBridgeHold, DesktopConfig,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_host import (
    main as host_main,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_preload_admission import (
    PreloadAdmission, PreloadAdmissionHold, PreloadPolicy,
    evaluate_preload, check_fresh_native_preload,
    verify_public_preload_receipt,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_protocol import (
    response,
)

MIB = 1024**2
GIB = 1024**3
MODEL = "a" * 64


def model(*, size=2*GIB, rights=True, verified=True):
    return InstalledModelReport(
        model_id="real_source_fixture",
        model_sha256=MODEL,
        manifest_sha256="b"*64,
        shard_count=1,
        model_bytes=size,
        rights_approved=rights,
        content_verified=verified,
        native_inference_tested=False,
        release_certified=False,
        archive_sha256="c"*64, source_sha="d"*40,
    )


def host(*, ram=12*GIB, disk=8*GIB):
    return {
        "schema": "laptop-device-observation.v1",
        "memory_total_bytes": 24*GIB,
        "memory_available_bytes": ram,
        "swap_free_bytes": 32*GIB,
        "state_storage_available_bytes": disk,
        "measurement_only": True,
        "qualified_device": False,
    }


def cgroup(*, ram=10*GIB, cpu=4):
    return CgroupObservation(
        memory_available_bytes=ram,
        cpu_quota_cores=cpu,
        memory_bounded=ram is not None,
        cpu_bounded=cpu is not None,
        source="cgroup-v2",
    )


def admitted(**override):
    args = dict(
        available_cores=8,
        n_ctx=4096,
        max_new_tokens=512,
        n_threads=2,
        gpu_layers=0,
        capacity_budget_bytes=8*GIB,
        inference_ms=90000,
    )
    args.update(override)
    return evaluate_preload(
        model(), host(), cgroup(), **args,
    )


class NativePreloadPolicyTests(unittest.TestCase):
    def test_healthy_real_cpu_ram_controller_model_and_disk_allow_no_auto_resize(self):
        proof = admitted()
        self.assertEqual(proof.model_sha256, MODEL)
        self.assertEqual(proof.model_bytes, 2*GIB)
        self.assertEqual(proof.effective_available_bytes, 10*GIB)
        self.assertEqual(proof.selected_cpu_threads, 2)
        self.assertEqual(proof.available_cpu_cores, 4)
        self.assertEqual(proof.requested_context_tokens, 4096)
        self.assertEqual(proof.requested_output_tokens, 512)
        self.assertEqual(proof.requested_gpu_layers, 0)
        self.assertLess(proof.estimated_working_bytes, proof.capacity_budget_bytes)
        self.assertLess(
            proof.estimated_working_bytes + proof.reserved_system_bytes,
            proof.effective_available_bytes,
        )
        public = proof.to_public()
        self.assertTrue(public["preload_estimate_not_native_proof"])
        self.assertFalse(public["gpu_vram_verified"])
        self.assertFalse(public["physical_device_qualified"])
        self.assertFalse(public["real_native_generation_executed"])
        self.assertFalse(public["release_certified"])
        self.assertNotIn("/private/", repr(public))

    def test_model_larger_than_effective_cgroup_memory_denied_before_native(self):
        with self.assertRaises(PreloadAdmissionHold):
            evaluate_preload(
                model(size=3*GIB), host(ram=16*GIB),
                cgroup(ram=2*GIB, cpu=4),
                available_cores=8,
                n_ctx=2048, max_new_tokens=256, n_threads=2,
                gpu_layers=0, capacity_budget_bytes=8*GIB,
            )

    def test_high_context_working_set_cannot_ignore_kv_memory_growth(self):
        with self.assertRaises(PreloadAdmissionHold):
            admitted(n_ctx=131072, max_new_tokens=8192)

    def test_cpu_thread_request_beyond_real_cgroup_quota_is_denied(self):
        with self.assertRaises(PreloadAdmissionHold):
            evaluate_preload(
                model(), host(), cgroup(cpu=1),
                available_cores=16, n_ctx=2048, max_new_tokens=256,
                n_threads=2, gpu_layers=0, capacity_budget_bytes=8*GIB,
            )

    def test_finite_capacity_budget_cannot_invent_native_swap_capacity(self):
        with self.assertRaises(PreloadAdmissionHold):
            admitted(capacity_budget_bytes=1*GIB)

    def test_state_sqlite_disk_floor_is_checked_before_model_loader(self):
        with self.assertRaises(PreloadAdmissionHold):
            evaluate_preload(
                model(), host(disk=100*MIB), cgroup(),
                available_cores=8, n_ctx=2048, max_new_tokens=256,
                n_threads=2, gpu_layers=0, capacity_budget_bytes=8*GIB,
            )

    def test_no_independent_model_rights_from_unreviewed_archive(self):
        for original in (model(rights=False), model(verified=False)):
            with self.subTest(original=original), self.assertRaises(PreloadAdmissionHold):
                evaluate_preload(
                    original, host(), cgroup(),
                    available_cores=8, n_ctx=2048, max_new_tokens=256,
                    n_threads=2, gpu_layers=0, capacity_budget_bytes=8*GIB,
                )

    def test_boolean_unbounded_unknown_host_evidence_is_held(self):
        for measurement in (
            None, {}, host(ram=True), host(ram=-1),
            dict(host(), measurement_only=False),
            dict(host(), qualified_device=True),
            dict(host(), state_storage_available_bytes="unlimited"),
        ):
            with self.subTest(measurement=measurement), self.assertRaises(PreloadAdmissionHold):
                evaluate_preload(
                    model(), measurement, cgroup(),
                    available_cores=8, n_ctx=2048, max_new_tokens=256,
                    n_threads=2, gpu_layers=0, capacity_budget_bytes=8*GIB,
                )

    def test_operator_policy_cannot_remove_ram_disk_reserves(self):
        for invalid in (
            {"minimum_ram_headroom_bytes": True},
            {"minimum_ram_headroom_bytes": -1},
            {"minimum_state_free_bytes": 0},
            {"minimum_system_reserve_bytes": 0},
            {"estimated_kv_bytes_per_token": 0},
            {"minimum_native_scratch_bytes": 4*GIB,
             "maximum_native_scratch_bytes": 512*MIB},
            {"thread_scratch_bytes": False},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(PreloadAdmissionHold):
                PreloadPolicy(**invalid)


class NativeStartupReceiptTests(unittest.TestCase):
    def setUp(self):
        self.proof = admitted()
        self.source = self.proof.to_public()
        self.opts = dict(
            expected_model_sha256=MODEL,
            requested_context_tokens=4096,
            requested_output_tokens=512,
            requested_cpu_threads=2,
            requested_gpu_layers=0,
            requested_capacity_budget_bytes=8*GIB,
        )

    def test_parent_receipt_reconstructs_exact_original_native_config(self):
        checked = verify_public_preload_receipt(self.source, **self.opts)
        self.assertIsInstance(checked, PreloadAdmission)
        self.assertEqual(checked.to_public(), self.source)

    def test_tampering_or_overstated_device_pass_is_refused(self):
        for tamper in (
            {"model_sha256": "f"*64},
            {"measured_host_available_bytes": True},
            {"effective_available_bytes": -1},
            {"estimated_working_bytes": 100*GIB},
            {"reserved_system_bytes": 0},
            {"selected_cpu_threads": 9},
            {"requested_context_tokens": 2048},
            {"requested_gpu_layers": 4},
            {"capacity_budget_bytes": 9999},
            {"gpu_vram_verified": True},
            {"physical_device_qualified": True},
            {"release_certified": True},
            {"unknown_authority": True},
            {"preload_estimate_not_native_proof": False},
        ):
            with self.subTest(tamper=tamper):
                modified = dict(self.source, **tamper)
                with self.assertRaises(PreloadAdmissionHold):
                    verify_public_preload_receipt(modified, **self.opts)

    def test_host_disallows_preload_pass_from_different_config(self):
        for changed in (
            {"requested_output_tokens": 256},
            {"requested_cpu_threads": 3},
            {"requested_capacity_budget_bytes": 2*GIB},
        ):
            with self.subTest(changed=changed), self.assertRaises(PreloadAdmissionHold):
                verify_public_preload_receipt(
                    self.source, **dict(self.opts, **changed),
                )

    def test_source_only_parent_accepts_actual_typed_preload_receipt(self):
        config = DesktopConfig(
            model_root="/private/model", state_dir="/private/state",
            tenant="local", subject="owner", context=4096,
            max_output_tokens=512, threads=2,
            capacity_budget_bytes=8*GIB,
            enable_pressure_guard=True,
        )
        bridge = DesktopBridge(config)
        self.assertIn("--enforce-preload-safety", config.worker_args())
        ready = response(
            "native-gguf-ready",
            session_id="s_actual_owner1", model_sha256=MODEL,
            tenant="local", subject="owner",
            source_bound=True, physical_device_qualified=False,
            signed_source_tool_active=False,
            signed_source_manifest_sha256=None,
            preload_admission=self.source,
        )
        verified = bridge._verify(ready)
        self.assertEqual(verified["preload_admission"], self.source)
        self.assertEqual(bridge.model_sha256, MODEL)

    def test_parent_refuses_omitted_or_wrong_preload_when_guard_enabled(self):
        config = DesktopConfig(
            model_root="/private/model", state_dir="/private/state",
            tenant="local", subject="owner", context=4096,
            max_output_tokens=512, threads=2,
            capacity_budget_bytes=8*GIB,
            enable_pressure_guard=True,
        )
        for preload in (None, {"schema": "unknown"}, dict(self.source, release_certified=True)):
            with self.subTest(preload=preload), self.assertRaises(DesktopBridgeHold):
                bridge = DesktopBridge(config)
                bridge._verify(response(
                    "native-gguf-ready", session_id="s_owner",
                    model_sha256=MODEL, tenant="local", subject="owner",
                    source_bound=True, physical_device_qualified=False,
                    signed_source_tool_active=False,
                    signed_source_manifest_sha256=None,
                    preload_admission=preload,
                ))

    def test_default_legacy_parent_does_not_create_new_implicit_resource_grant(self):
        config = DesktopConfig(
            model_root="/private/model", state_dir="/private/state",
            tenant="local", subject="owner",
        )
        self.assertNotIn("--enforce-preload-safety", config.worker_args())


class RealHostPreloadOrderTests(unittest.TestCase):
    def test_failing_live_pressure_check_never_calls_native_model_loader(self):
        args = [
            "--approve-native", "--enforce-preload-safety",
            "--model-root", "/private/model",
            "--state-dir", "/private/state",
            "--tenant", "local", "--subject", "owner",
            "--context", "4096", "--max-output-tokens", "512",
            "--threads", "2", "--capacity-budget-bytes", str(8*GIB),
        ]
        stderr = StringIO()
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_preload_admission.check_fresh_native_preload",
                side_effect=PreloadAdmissionHold("private model path /home/owner"),
            ) as resource,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_host.activate_checked",
            ) as native,
            redirect_stderr(stderr),
        ):
            code = host_main(args)
        self.assertEqual(code, 2)
        resource.assert_called_once()
        native.assert_not_called()
        self.assertNotIn("/home/owner", stderr.getvalue())
        self.assertIn("PreloadAdmissionHold", stderr.getvalue())

    def test_existing_real_source_checks_run_before_native_activation(self):
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_preload_admission.source_receipt",
                return_value=model(),
            ) as verify_source,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_preload_admission.inspect_device",
                return_value=host(),
            ) as observe,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_preload_admission.observe_cgroup",
                return_value=cgroup(),
            ) as quota,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_preload_admission.observe_cpu",
                return_value=8,
            ) as cpu,
        ):
            result = check_fresh_native_preload(
                model_root=Path("/private/model"),
                state_dir=Path("/private/state"),
                n_ctx=4096, max_new_tokens=512,
                n_threads=2, gpu_layers=0,
                capacity_budget_bytes=8*GIB,
            )
        self.assertEqual(result.model_sha256, MODEL)
        verify_source.assert_called_once()
        self.assertEqual(verify_source.call_args.kwargs["require_rights"], True)
        observe.assert_called_once()
        quota.assert_called_once()
        cpu.assert_called_once()
        self.assertFalse(result.to_public()["real_native_generation_executed"])


if __name__ == "__main__":
    unittest.main()
