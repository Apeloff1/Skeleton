"""Regression fixtures for selected-source capsules and the escrow CLI.

Synthetic disposable projects only: no native model request, network, Git,
execution of model source, or original checkout write during publication.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
    desktop_patch_bundle as bundle,
    desktop_private_capsule as capsule,
    desktop_native_capsule_cli as cli,
)


def _new(*files):
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [{"path": p, "content": s} for p, s in files],
    })


def _edit(*rows):
    return json.dumps({
        "schema": edits.SCHEMA,
        "files": [
            {"path": p, "expected_sha256": sha256(old.encode()).hexdigest(),
             "replacement": new}
            for p, old, new in rows
        ],
    })


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Selected-source capsule requires POSIX/WSL2 owner-private descriptors",
)
class PrivateSelectedSourceCapsuleTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="jeeves-source-capsule-")
        self.addCleanup(t.cleanup)
        self.top = Path(t.name)
        self.project = self.top / "project"
        self.project.mkdir(mode=0o700)
        self.src = self.project / "src"
        self.src.mkdir(mode=0o700)
        self.private = self.top / "private"
        self.private.mkdir(mode=0o700)
        self.output = self.private / "verified-source-capsule"
        self.app = self.src / "app.py"
        self.dep = self.src / "dependency.py"
        self.app.write_text("from .dependency import value\nresult = value\n")
        self.dep.write_text("value = 12\n")

        def open_root(path):
            return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

        # CI ephemeral /tmp ancestors are shared; mock only the original
        # trusted-root resolution, never original path checks or inode reads.
        for module in (workspace, edits, bundle, capsule):
            patcher = mock.patch.object(module, "_open_root", side_effect=open_root)
            patcher.start()
            self.addCleanup(patcher.stop)
        private = mock.patch.object(
            capsule, "_pinned_private_directory",
            side_effect=lambda path: open_root(path.parent),
        )
        private.start()
        self.addCleanup(private.stop)

    def patch(self):
        return bundle.review_patch_bundle(
            self.project,
            new_files=_new(
                ("src/fresh.py", "from .dependency import value\nanswer = value + 1\n"),
                ("README.md", "# New generated file\n"),
            ),
            existing_edits=_edit(
                ("src/app.py", self.app.read_text(),
                 "from .dependency import value\nresult = value + 1\n"),
            ),
        )

    def prepare(self, include="src/dependency.py"):
        return capsule.prepare_private_capsule(self.patch(), include)

    def publish(self, plan, **overrides):
        kwargs = {
            "expected_capsule_sha256": plan.capsule_sha256,
            "expected_manifest_sha256": plan.patch.manifest_sha256,
            "expected_patch_sha256": plan.patch.patch_sha256,
            "approve_private_capsule": True,
        }
        kwargs.update(overrides)
        return capsule.publish_private_capsule(plan, self.output, **kwargs)

    def test_mixed_source_capsule_is_finite_sealed_and_original_unchanged(self):
        before = {p: p.read_bytes() for p in (self.app, self.dep)}
        plan = self.prepare()
        with (
            mock.patch("subprocess.Popen") as popen,
            mock.patch("subprocess.run") as shell,
            mock.patch("os.system") as system,
        ):
            result = self.publish(plan)
            popen.assert_not_called()
            shell.assert_not_called()
            system.assert_not_called()
        self.assertEqual(result["file_count"], 4)
        self.assertEqual(result["capsule_sha256"], plan.capsule_sha256)
        self.assertTrue(result["all_source_bytes_read_back"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.output / "src/dependency.py").read_bytes(), before[self.dep])
        self.assertIn(b"value + 1", (self.output / "src/app.py").read_bytes())
        self.assertTrue((self.output / "src/fresh.py").is_file())
        self.assertTrue((self.output / "README.md").is_file())
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        seal = json.loads((self.output / capsule.SEAL_NAME).read_bytes())
        self.assertEqual(seal["capsule_sha256"], plan.capsule_sha256)
        self.assertEqual(len(seal["files"]), 4)
        self.assertEqual(
            result["seal_sha256"],
            sha256((self.output / capsule.SEAL_NAME).read_bytes()).hexdigest(),
        )
        for p in self.output.rglob("*"):
            if p.is_file():
                self.assertEqual(p.stat().st_mode & 0o077, 0)

    def test_new_export_is_never_silent_overwrite(self):
        plan = self.prepare()
        self.publish(plan)
        previous = (self.output / capsule.SEAL_NAME).read_bytes()
        with self.assertRaises(FileExistsError):
            self.publish(plan)
        self.assertEqual(previous, (self.output / capsule.SEAL_NAME).read_bytes())

    def test_existing_source_drift_has_no_written_capsule(self):
        plan = self.prepare()
        self.app.write_text("result = 999\n")
        with self.assertRaises((ValueError, OSError)):
            self.publish(plan)
        self.assertFalse(self.output.exists())

    def test_selected_original_drift_has_no_written_capsule(self):
        plan = self.prepare()
        self.dep.write_text("value = 987\n")
        with self.assertRaises((ValueError, OSError)):
            self.publish(plan)
        self.assertFalse(self.output.exists())

    def test_bad_consent_and_full_sha_are_rejected_before_fs_write(self):
        plan = self.prepare()
        for field, value in (
            ("approve_private_capsule", False),
            ("expected_capsule_sha256", "0" * 64),
            ("expected_manifest_sha256", "0" * 64),
            ("expected_patch_sha256", "0" * 64),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.publish(plan, **{field: value})
                self.assertFalse(self.output.exists())

    def test_credential_paths_duplicate_paths_and_edit_conflicts_denied(self):
        plan = self.patch()
        invalid = (
            "src/app.py", "src/dependency.py\nsrc/dependency.py",
            "src/../secret.py", ".github/workflows/a.yml", "src/.env",
            "src/missing.py", "src/dependency.py\r",
        )
        for entry in invalid:
            with self.subTest(entry=entry):
                with self.assertRaises((ValueError, OSError)):
                    capsule.prepare_private_capsule(plan, entry)

    def test_symlinked_selected_original_is_not_followed(self):
        plan = self.patch()
        self.dep.unlink()
        self.dep.symlink_to(self.app)
        with self.assertRaises((ValueError, OSError)):
            capsule.prepare_private_capsule(plan, "src/dependency.py")
        self.assertFalse(self.output.exists())

    def test_oversized_source_and_changed_plan_digest_rejected(self):
        plan = self.prepare()
        with self.assertRaises(ValueError):
            replace(plan, capsule_sha256="f" * 64).__post_init__()
        with self.assertRaises(ValueError):
            replace(plan, total_bytes=plan.total_bytes - 1).__post_init__()

    def test_crash_before_seal_leaves_visibly_incomplete_private_directory(self):
        plan = self.prepare()
        original_copy = capsule._copy
        def fail_before_seal(fd, relative, content, expected):
            if relative == capsule.SEAL_NAME:
                raise OSError("simulated power loss")
            return original_copy(fd, relative, content, expected)
        with mock.patch.object(capsule, "_copy", side_effect=fail_before_seal):
            with self.assertRaises(OSError):
                self.publish(plan)
        self.assertTrue(self.output.is_dir())
        self.assertFalse((self.output / capsule.SEAL_NAME).exists())
        with self.assertRaises(FileExistsError):
            self.publish(plan)

    def test_destination_inside_checkout_or_symlink_denied(self):
        plan = self.prepare()
        with self.assertRaises(ValueError):
            capsule.publish_private_capsule(
                plan, self.project / "bad",
                expected_capsule_sha256=plan.capsule_sha256,
                expected_manifest_sha256=plan.patch.manifest_sha256,
                expected_patch_sha256=plan.patch.patch_sha256,
                approve_private_capsule=True,
            )
        (self.private / "verified-source-capsule").symlink_to(self.project)
        with self.assertRaises((ValueError, OSError)):
            self.publish(plan)
        self.assertFalse((self.project / capsule.SEAL_NAME).exists())


    def test_complete_capsule_cold_verification_matches_every_source_byte(self):
        plan = self.prepare()
        stage = self.publish(plan)
        with (
            mock.patch("subprocess.Popen") as process,
            mock.patch("subprocess.run") as shell,
        ):
            outcome = capsule.verify_private_capsule(
                self.output, original_project_root=str(self.project),
                expected_capsule_sha256=plan.capsule_sha256,
                expected_seal_sha256=stage["seal_sha256"],
            )
            process.assert_not_called()
            shell.assert_not_called()
        self.assertEqual(outcome["file_count"], 4)
        self.assertTrue(outcome["all_sealed_source_bytes_verified"])
        self.assertFalse(outcome["release_certified"])

    def test_capsule_verifier_rejects_changed_source_and_seal(self):
        plan = self.prepare()
        stage = self.publish(plan)
        path = self.output / "src/fresh.py"
        path.write_text("altered source bytes\n")
        with self.assertRaises((ValueError, OSError)):
            capsule.verify_private_capsule(
                self.output, original_project_root=str(self.project),
                expected_capsule_sha256=plan.capsule_sha256,
                expected_seal_sha256=stage["seal_sha256"],
            )

    def test_capsule_verifier_rejects_added_unapproved_file(self):
        plan = self.prepare()
        stage = self.publish(plan)
        (self.output / "src/hidden.py").write_bytes(b"secret = 1\n")
        with self.assertRaises((ValueError, OSError)):
            capsule.verify_private_capsule(
                self.output, original_project_root=str(self.project),
                expected_capsule_sha256=plan.capsule_sha256,
                expected_seal_sha256=stage["seal_sha256"],
            )

    def test_capsule_verifier_rejects_symlink_tree_entry(self):
        plan = self.prepare()
        stage = self.publish(plan)
        (self.output / "src/alias.py").symlink_to("fresh.py")
        with self.assertRaises((ValueError, OSError)):
            capsule.verify_private_capsule(
                self.output, original_project_root=str(self.project),
                expected_capsule_sha256=plan.capsule_sha256,
                expected_seal_sha256=stage["seal_sha256"],
            )

    def test_capsule_verifier_rejects_seal_replacement_and_digest_mismatch(self):
        plan = self.prepare()
        stage = self.publish(plan)
        verify = lambda **kw: capsule.verify_private_capsule(
            self.output, original_project_root=str(self.project),
            expected_capsule_sha256=plan.capsule_sha256,
            expected_seal_sha256=stage["seal_sha256"], **kw,
        )
        with self.assertRaises((ValueError, OSError)):
            capsule.verify_private_capsule(
                self.output, original_project_root=str(self.project),
                expected_capsule_sha256="0" * 64,
                expected_seal_sha256=stage["seal_sha256"],
            )
        path = self.output / capsule.SEAL_NAME
        seal = json.loads(path.read_bytes())
        seal["release_certified"] = True
        path.write_text(json.dumps(seal))
        with self.assertRaises((ValueError, OSError)):
            verify()

    def test_verifier_refuses_incomplete_unsealed_capsule(self):
        plan = self.prepare()
        original_copy = capsule._copy
        def no_seal(fd, relative, data, digest):
            if relative == capsule.SEAL_NAME:
                raise OSError("simulated crash before seal")
            return original_copy(fd, relative, data, digest)
        with mock.patch.object(capsule, "_copy", side_effect=no_seal):
            with self.assertRaises(OSError):
                self.publish(plan)
        with self.assertRaises((ValueError, OSError)):
            capsule.verify_private_capsule(
                self.output, original_project_root=str(self.project),
                expected_capsule_sha256=plan.capsule_sha256,
                expected_seal_sha256="0" * 64,
            )


    def test_real_mixed_source_private_capsule_binds_original_imports_to_seal(self):
        plan = self.prepare()
        review = plan.public_review()
        self.assertEqual(review["linked_original_imports"], 2)
        self.assertEqual(review["linked_review_change_imports"], 0)
        self.assertEqual(review["unverified_external_or_unselected_imports"], 0)
        self.assertEqual(review["selected_python_closure_status"], "linked-selected-python")
        receipt = self.publish(plan)
        self.assertEqual(
            receipt["python_closure_sha256"], plan.python_closure_sha256,
        )
        seal = json.loads((self.output / capsule.SEAL_NAME).read_bytes())
        self.assertEqual(seal["unverified_source_import_count"], 0)
        verified = capsule.verify_private_capsule(
            self.output, original_project_root=str(self.project),
            expected_capsule_sha256=plan.capsule_sha256,
            expected_seal_sha256=receipt["seal_sha256"],
        )
        self.assertEqual(verified["linked_original_source_imports"], 2)
        self.assertEqual(verified["python_closure_sha256"], plan.python_closure_sha256)

    def test_real_original_dependency_import_unknown_survives_publish_and_verify(self):
        self.dep.write_text("import external_library\nvalue = 4\n")
        plan = self.prepare()
        self.assertEqual(
            plan.public_review()["unverified_external_or_unselected_imports"], 1,
        )
        receipt = self.publish(plan)
        self.assertEqual(receipt["unverified_source_import_count"], 1)
        verified = capsule.verify_private_capsule(
            self.output, original_project_root=str(self.project),
            expected_capsule_sha256=plan.capsule_sha256,
            expected_seal_sha256=receipt["seal_sha256"],
        )
        self.assertEqual(verified["unverified_external_or_unselected_imports"], 1)
        self.assertFalse(verified["all_source_dependencies_complete"])

    def test_real_capsule_holds_original_dependency_with_invalid_relative_import(self):
        self.dep.write_text("from ...unreachable import thing\n")
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_source_closure_digest_mutation_cannot_publish(self):
        plan = self.prepare()
        # Identity tampering is rejected at dataclass construction, before any
        # publication API can receive an invalid source-closure grant.
        with self.assertRaises(capsule.PrivateCapsuleHold):
            replace(plan, python_closure_sha256="0"*64)
        self.assertFalse(self.output.exists())


class PrivateCapsuleCLITests(unittest.TestCase):
    def req(self, action="inspect"):
        return {
            "schema": cli.SCHEMA, "action": action,
            "project_root": "/project",
            "saved_proposal_file": "/private/original.source.json",
            "expected_saved_file_sha256": "a" * 64,
            "expected_saved_file_bytes": 400,
            "expected_job_sha256": "b" * 64,
            "selected_sources": "src/dependency.py",
            "target": None if action == "inspect" else "/private/capsule",
            "source_manifest_sha256": None if action == "inspect" else "c" * 64,
            "source_patch_sha256": None if action == "inspect" else "d" * 64,
            "capsule_sha256": None if action == "inspect" else "e" * 64,
        }

    def test_valid_two_phase_parser_and_distinct_authority(self):
        for action in ("inspect", "publish"):
            self.assertEqual(
                cli.parse_capsule_request(json.dumps(self.req(action)).encode())["action"],
                action,
            )
        req = self.req()
        req["target"] = "/private/wrong"
        with self.assertRaises(ValueError):
            cli.parse_capsule_request(json.dumps(req).encode())

    def test_json_duplicate_unknown_nonfinite_and_boolean_bytes_fail_closed(self):
        cases = [
            b'{"schema":1,"schema":2}',
            b'{"schema":NaN}',
            b'\xff',
            json.dumps({**self.req(), "other": 1}).encode(),
            json.dumps({**self.req(), "expected_saved_file_bytes": True}).encode(),
            json.dumps({**self.req(), "selected_sources": ""}).encode(),
        ]
        for raw in cases:
            with self.subTest(raw=raw[:80]):
                with self.assertRaises(ValueError):
                    cli.parse_capsule_request(raw)

    def test_inspect_does_not_publish_and_publish_checks_three_sha(self):
        plan = SimpleNamespace(
            capsule_sha256="e"*64,
            patch=SimpleNamespace(manifest_sha256="c"*64, patch_sha256="d"*64),
            public_review=lambda: {"capsule_sha256": "e"*64},
        )
        reviewed = SimpleNamespace(
            source_plan=plan.patch, private_file_sha256="a"*64,
            job_sha256="b"*64, model_sha256="f"*64,
            source_manifest_sha256="c"*64, patch_sha256="d"*64,
        )
        with (
            mock.patch.object(cli, "inspect_saved_native_source", return_value=reviewed),
            mock.patch.object(cli, "prepare_private_capsule", return_value=plan),
            mock.patch.object(cli, "publish_private_capsule", return_value={"ok": True}) as pub,
        ):
            outcome = cli.execute_capsule_request(self.req())
            self.assertEqual(outcome["action"], "inspect")
            self.assertIsNone(outcome["publication"])
            pub.assert_not_called()
            with self.assertRaises(ValueError):
                cli.execute_capsule_request(self.req("publish"))
            result = cli.execute_capsule_request(
                self.req("publish"), approve_private_capsule=True,
            )
            self.assertEqual(result["publication"], {"ok": True})
            self.assertFalse(result["native_inference_executed"])
            pub.assert_called_once()

    def test_stderr_redacted_on_any_failure_and_no_stdout(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        result = cli.main(
            [], stdin=io.BytesIO(b"invalid source"), stdout=stdout, stderr=stderr,
        )
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "JEEVES_PRIVATE_SOURCE_CAPSULE_HELD\n")


from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_capsule_verifier_cli as verifier,
)


class PrivateCapsuleVerifierCLITests(unittest.TestCase):
    def req(self):
        return {
            "schema": verifier.SCHEMA,
            "capsule_directory": "/private/project-review",
            "original_project_root": "/project",
            "expected_capsule_sha256": "a" * 64,
            "expected_seal_sha256": "b" * 64,
        }

    def test_read_only_verified_receipt_and_no_hidden_side_effects(self):
        req = self.req()
        with mock.patch.object(
            verifier, "verify_private_capsule",
            return_value={"all_sealed_source_bytes_verified": True},
        ) as verification:
            result = verifier.execute_verification(req)
            self.assertEqual(
                result["verification"]["all_sealed_source_bytes_verified"], True,
            )
            self.assertFalse(result["model_or_git_invoked"])
            self.assertFalse(result["release_certified"])
            verification.assert_called_once()

    def test_strict_verifier_rejects_duplicate_unknown_and_nonfinite(self):
        for raw in (
            b'{"schema":1,"schema":2}',
            b'{"schema":NaN}',
            json.dumps({**self.req(), "extra": 1}).encode(),
            json.dumps({**self.req(), "expected_seal_sha256": False}).encode(),
            json.dumps({**self.req(), "capsule_directory": "relative"}).encode(),
        ):
            with self.subTest(raw=raw[:75]):
                with self.assertRaises(ValueError):
                    verifier.parse_verification(raw)

    def test_private_verifier_stdout_is_blank_on_failure(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        status = verifier.main(
            [], stdin=io.BytesIO(b"invalid verification"),
            stdout=stdout, stderr=stderr,
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(), "JEEVES_PRIVATE_CAPSULE_VERIFICATION_HELD\n",
        )


if __name__ == "__main__":
    unittest.main()
