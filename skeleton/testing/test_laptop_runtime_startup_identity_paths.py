"""Fail-closed installed GGUF startup before private prompt or SQLite I/O.

No test here installs model weights or runs a native GGUF child. The
installer, activation and token worker are explicit deterministic doubles.
"""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.testing.laptop_runtime_test_support import FakeWorker


def options(**updates):
    result = {
        "model_root": "/approved/model", "state_dir": "/private/sqlite",
        "tenant": "local", "subject": "owner",
        "capacity_root": "/private/leases",
    }
    result.update(updates)
    return result


def approved(**updates):
    receipt = dict(
        model_sha256="a" * 64, content_verified=True,
        rights_approved=True, archive_sha256="b" * 64,
        source_sha="c" * 40,
    )
    receipt.update(updates)
    return SimpleNamespace(**receipt)


class StartupIdentityAndPathTests(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.closed = []
        self.calls = []

    def activate(self, **kwargs):
        self.calls.append(("activate", kwargs))
        stack = ExitStack()
        stack.callback(lambda: self.closed.append("closed"))
        return stack, self.worker

    def run_checked(self, **kwargs):
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model",
                return_value=approved(),
            ) as doctor,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.deployment.production.startup.activate",
                side_effect=self.activate,
            ) as native,
        ):
            return activate_checked(**options(**kwargs)), doctor, native

    def test_installed_source_inspected_before_native_activation(self):
        (stack, worker, receipt), doctor, native = self.run_checked()
        self.assertIs(worker, self.worker)
        doctor.assert_called_once_with("/approved/model")
        native.assert_called_once()
        self.assertIs(receipt.rights_approved, True)
        stack.close()
        self.assertEqual(self.closed, ["closed"])

    def test_foreign_activated_tenant_is_held_and_closed(self):
        self.worker.spine.identity.tenant = "foreign"
        with self.assertRaises(ContractViolation):
            self.run_checked()
        self.assertEqual(self.closed, ["closed"])
        self.assertEqual(len(self.calls), 1)

    def test_foreign_subject_is_held_and_closed(self):
        self.worker.spine.identity.subject = "intruder"
        with self.assertRaises(ContractViolation):
            self.run_checked()
        self.assertEqual(self.closed, ["closed"])

    def test_model_digest_mismatch_closes_stack(self):
        self.worker.spine.identity.model_sha256 = "f" * 64
        with self.assertRaises(ContractViolation):
            self.run_checked()
        self.assertEqual(self.closed, ["closed"])

    def test_tokenizer_digest_mismatch_closes_stack(self):
        self.worker.spine.backend.tokenizer_digest = "f" * 64
        with self.assertRaises(ContractViolation):
            self.run_checked()
        self.assertEqual(self.closed, ["closed"])

    def test_verified_path_typed_as_pathlib_is_accepted(self):
        (stack, worker, _), _, native = self.run_checked(
            model_root=Path("/approved/model"),
            state_dir=Path("/private/sqlite"),
            capacity_root=Path("/private/leases"),
        )
        self.assertIs(worker, self.worker)
        self.assertIs(native.call_args.kwargs["model_root"], native.call_args.kwargs["model_root"])
        stack.close()

    def test_invalid_model_roots_fail_before_installer_or_native_io(self):
        invalid = (None, "", "relative/model", "/tmp/../model",
                   "/private/\x00hidden", b"/model", 123, True)
        for value in invalid:
            with self.subTest(value=repr(value)):
                with (
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model",
                    ) as doctor,
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.production.startup.activate",
                    ) as native,
                ):
                    with self.assertRaises((ContractViolation, ValueError)):
                        activate_checked(**options(model_root=value))
                    doctor.assert_not_called()
                    native.assert_not_called()

    def test_state_and_capacity_roots_fail_before_installer(self):
        for key in ("state_dir", "capacity_root"):
            for value in ("relative", "/private/../escaped", "/\x00bad", [], False):
                with self.subTest(key=key, value=repr(value)):
                    with (
                        mock.patch(
                            "skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model",
                        ) as doctor,
                        mock.patch(
                            "skeleton.ai.runtime.operational_ai.deployment.production.startup.activate",
                        ) as native,
                    ):
                        with self.assertRaises((ContractViolation, ValueError)):
                            activate_checked(**options(**{key: value}))
                        doctor.assert_not_called()
                        native.assert_not_called()

    def test_unapproved_or_bool_coerced_receipts_do_not_start_native(self):
        for change in (
            {"rights_approved": False}, {"rights_approved": 1},
            {"content_verified": False}, {"content_verified": 1},
            {"source_sha": ""}, {"archive_sha256": ""},
        ):
            with self.subTest(change=change):
                with (
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model",
                        return_value=approved(**change),
                    ),
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.production.startup.activate",
                    ) as native,
                ):
                    with self.assertRaises(ContractViolation):
                        activate_checked(**options())
                    native.assert_not_called()

    def test_invalid_shape_never_inspects_approved_weights(self):
        for override in (
            {"n_ctx": 32}, {"n_threads": 0}, {"max_new_tokens": 999999},
            {"gpu_layers": -1}, {"inference_ms": 99}, {"isolated": False},
        ):
            with self.subTest(override=override):
                with (
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model",
                    ) as doctor,
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.production.startup.activate",
                    ) as native,
                ):
                    with self.assertRaises(ContractViolation):
                        activate_checked(**options(**override))
                    doctor.assert_not_called()
                    native.assert_not_called()

    def test_path_exception_is_redacted_without_echoing_private_root(self):
        secret_path = "/private/owner-confidential/../archive"
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model"
        ) as doctor:
            with self.assertRaises(ContractViolation) as caught:
                activate_checked(**options(model_root=secret_path))
        self.assertNotIn("owner-confidential", str(caught.exception))
        doctor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
