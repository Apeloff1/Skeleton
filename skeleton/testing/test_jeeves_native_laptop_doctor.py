"""First-laptop read-only source/model/state readiness with real SQLite.

The model inspection is TEST-ONLY stubbed: these tests must never be
presented as GGUF inference, original rights, device pressure or Windows
installation proof. Private DB access uses actual protected SQLite/WAL.
"""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.deployment.install.doctor import InstalledModelReport
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity,SpineLimits
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.agent.native_durable_batch import NativeDurableBatchConveyor
from skeleton.jeeves.native_fabric.delivery_outbox import NativeDeliveryOutbox
from skeleton.jeeves.native_fabric.laptop_doctor import (
    NativeLaptopHold,inspect_laptop,main,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL,TOKENIZER,SyntheticallyGenerated,
)


class TestNativeLaptopDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=SpineDatabase(self.tmp.name)
        self.gate=SessionGate(self.tmp.name)
        self.addCleanup(self.gate.close)
        self.addCleanup(self.db.close)
        self.backend=SyntheticallyGenerated()
        self.worker=SupervisedAI(ExecutionSpine(
            db=self.db,session_gate=self.gate,backend=self.backend,
            identity=Identity("local","operator",MODEL,TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768,response_bytes=131072,
                max_output_tokens=128,context_tokens=4096,
            ),
        ))
        native=NativeDurableBatchConveyor(self.worker,approved=True)
        NativeDeliveryOutbox(
            native.queue,receiver_id="laptop_screen",
            receiver_key=bytes.fromhex("c1"*32),
        )
        self.installed=InstalledModelReport(
            model_id="approved-local",
            model_sha256=MODEL,
            manifest_sha256="e"*64,
            shard_count=1,
            model_bytes=2147483648,
            rights_approved=True,
            content_verified=True,
            archive_sha256="f"*64,
            source_sha="1"*40,
        )
        self.device={
            "schema":"laptop-device-observation.v1",
            "memory_total_bytes":17179869184,
            "memory_available_bytes":8589934592,
            "swap_free_bytes":4294967296,
            "state_storage_available_bytes":21474836480,
            "measurement_only":True,
            "qualified_device":False,
        }

    def call(self,*,installed=None,device=None,doctor=None,model_root=Path("/approved/installed")):
        with (
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_installed_model",
                return_value=self.installed if installed is None else installed,
            ) as installer,
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_device",
                return_value=self.device if device is None else device,
            ),
        ):
            return inspect_laptop(
                model_root=model_root,state_dir=Path(self.tmp.name),
                tenant="local",subject="operator",
                model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
            )

    def test_real_sqlite_state_and_approved_fixture_are_inspected_without_inference(self):
        report=self.call()
        self.assertTrue(report.protected_runtime_state_verified)
        self.assertTrue(report.installation_source_verified)
        self.assertTrue(report.operator_rights_receipt)
        self.assertTrue(report.memory_floor_met)
        self.assertTrue(report.disk_floor_met)
        self.assertEqual(self.backend.calls,0)
        self.assertFalse(report.eligible_for_manual_native_acceptance)

    def test_physical_model_and_license_are_never_declared_proven(self):
        record=self.call().to_public_record()
        self.assertFalse(record["actual_native_model_loaded"])
        self.assertFalse(record["physical_forward_pass_witnessed"])
        self.assertFalse(record["independent_model_license_review"])
        self.assertFalse(record["windows_11_wsl2_clean_install_qualified"])
        self.assertFalse(record["release_certified"])

    def test_operator_model_sha_mismatch_is_a_separate_hold(self):
        impostor=InstalledModelReport(
            model_id="other",model_sha256="d"*64,
            manifest_sha256="e"*64,shard_count=1,
            model_bytes=1000000000,rights_approved=True,content_verified=True,
            archive_sha256="f"*64,source_sha="1"*40,
        )
        report=self.call(installed=impostor)
        self.assertIn("installed_model_digest_mismatch",report.holds)

    def test_source_rights_hold_is_independent_from_byte_integrity(self):
        unlicensed=InstalledModelReport(
            model_id="unapproved",model_sha256=MODEL,
            manifest_sha256="e"*64,shard_count=1,model_bytes=100000,
            rights_approved=False,content_verified=True,
            archive_sha256="f"*64,source_sha="1"*40,
        )
        report=self.call(installed=unlicensed)
        self.assertTrue(report.installation_source_verified)
        self.assertFalse(report.operator_rights_receipt)
        self.assertIn("source_rights_not_approved",report.holds)

    def test_unavailable_model_root_is_reported_as_unqualified(self):
        with mock.patch(
            "skeleton.jeeves.native_fabric.laptop_doctor.inspect_device",
            return_value=self.device,
        ):
            report=inspect_laptop(
                model_root=None,state_dir=Path(self.tmp.name),
                tenant="local",subject="operator",
                model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
            )
        self.assertIn("installed_model_unavailable",report.holds)
        self.assertIsNone(report.installed_model_sha256)

    def test_failed_installer_does_not_disclose_private_model_path(self):
        with (
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_installed_model",
                side_effect=RuntimeError("/private/secret/weights/model.gguf"),
            ),
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_device",
                return_value=self.device,
            ),
        ):
            report=inspect_laptop(
                model_root=Path("/private/secret/weights"),
                state_dir=Path(self.tmp.name),
                tenant="local",subject="operator",
                model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
            )
        self.assertIn("installed_source_verification_failed",report.holds)
        self.assertNotIn("/private/secret",str(report.to_public_record()))

    def test_lower_observed_RAM_causes_separate_hold(self):
        bad={**self.device,"memory_available_bytes":134217728}
        report=self.call(device=bad)
        self.assertIn("insufficient_observed_memory",report.holds)
        self.assertTrue(report.disk_floor_met)

    def test_lower_observed_disk_causes_separate_hold(self):
        bad={**self.device,"state_storage_available_bytes":1048576}
        report=self.call(device=bad)
        self.assertIn("insufficient_observed_disk",report.holds)
        self.assertTrue(report.memory_floor_met)

    def test_missing_telemetry_never_counts_as_resource_pass(self):
        with (
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_installed_model",
                return_value=self.installed,
            ),
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_device",
                side_effect=ValueError("hidden host error"),
            ),
        ):
            report=inspect_laptop(
                model_root=Path("/approved/installed"),
                state_dir=Path(self.tmp.name),
                tenant="local",subject="operator",
                model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
            )
        self.assertIn("device_memory_or_disk_unknown",report.holds)
        self.assertIsNone(report.observed_available_ram_bytes)

    def test_missing_native_state_schema_is_reported_as_unavailable(self):
        other=tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        with (
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_installed_model",
                return_value=self.installed,
            ),
            mock.patch(
                "skeleton.jeeves.native_fabric.laptop_doctor.inspect_device",
                return_value=self.device,
            ),
        ):
            report=inspect_laptop(
                model_root=Path("/approved/installed"),
                state_dir=Path(other.name),
                tenant="local",subject="operator",
                model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
            )
        self.assertIn("protected_native_state_unavailable",report.holds)

    def test_malformed_sensor_record_does_not_clear_device_hold(self):
        bad={**self.device,"qualified_device":True}
        report=self.call(device=bad)
        self.assertIn("device_memory_or_disk_unknown",report.holds)

    def test_foreign_scope_has_different_scoped_doctor_identity(self):
        report=self.call()
        self.assertEqual(report.expected_model_sha256,MODEL)
        self.assertIsNotNone(report.cold_native_custody_sha256)
        self.assertEqual(len(report.cold_native_custody_sha256),64)

    def test_client_paths_are_never_leaked_to_operator_report(self):
        record=self.call().to_public_record()
        self.assertNotIn(self.tmp.name,str(record))
        self.assertNotIn("/approved/installed",str(record))

    def test_invalid_relative_model_path_rejected_before_any_installer_read(self):
        with mock.patch(
            "skeleton.jeeves.native_fabric.laptop_doctor.inspect_installed_model",
        ) as installer:
            with self.assertRaises(NativeLaptopHold):
                inspect_laptop(
                    model_root=Path("model"),
                    state_dir=Path(self.tmp.name),
                    tenant="local",subject="operator",
                    model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
                )
            installer.assert_not_called()

    def test_private_dotdot_path_rejected_without_resolution(self):
        with self.assertRaises(NativeLaptopHold):
            inspect_laptop(
                model_root=Path("/approved/../unsafe"),
                state_dir=Path(self.tmp.name),
                tenant="local",subject="operator",
                model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
            )

    def test_negative_or_bool_resource_floors_rejected(self):
        for floor in (-1,0,True,1.2):
            with self.subTest(floor=floor),self.assertRaises(NativeLaptopHold):
                inspect_laptop(
                    model_root=None,state_dir=Path(self.tmp.name),
                    tenant="local",subject="operator",
                    model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
                    minimum_available_ram_bytes=floor,
                )

    def test_no_runtime_model_generation_on_readonly_inspection(self):
        self.call()
        self.call()
        self.assertEqual(self.backend.calls,0)

    def test_fingerprint_does_not_contain_raw_private_state(self):
        record=self.call().to_public_record()
        self.assertIsNotNone(record["cold_native_custody_sha256"])
        self.assertNotIn("session_messages",str(record))
        self.assertNotIn("Jeeves user secret",str(record))

    def test_source_approval_does_not_override_all_other_laptop_holds(self):
        result=self.call()
        self.assertTrue(result.operator_rights_receipt)
        self.assertIn("active_tokenizer_identity_unverified",result.holds)
        self.assertIn("physical_native_inference_unverified",result.holds)
        self.assertIn("consumer_windows_install_unqualified",result.holds)

    def test_cli_malformed_path_never_echoes_private_args(self):
        out,err=StringIO(),StringIO()
        args=[
            "--model-root","/private/secret/model",
            "--state-dir","relative-state",
            "--tenant","local","--subject","operator",
            "--model-sha256",MODEL,"--tokenizer-sha256",TOKENIZER,
        ]
        with mock.patch("sys.stdout",out),mock.patch("sys.stderr",err):
            code=main(args)
        self.assertEqual(code,2)
        self.assertNotIn("/private/secret/model",err.getvalue())
        self.assertFalse(out.getvalue())

    def test_cli_source_only_proof_never_returns_exit_zero_as_release_pass(self):
        out,err=StringIO(),StringIO()
        args=[
            "--state-dir",self.tmp.name,"--tenant","local","--subject","operator",
            "--model-sha256",MODEL,"--tokenizer-sha256",TOKENIZER,
        ]
        with mock.patch("sys.stdout",out),mock.patch("sys.stderr",err),mock.patch(
            "skeleton.jeeves.native_fabric.laptop_doctor.inspect_device",
            return_value=self.device,
        ):
            code=main(args)
        self.assertEqual(code,3)
        self.assertIn("physical_native_inference_unverified",out.getvalue())
        self.assertNotIn(self.tmp.name,out.getvalue())


if __name__=="__main__":
    unittest.main()
