"""Native-generated private source escrow: source-only custody tests.

Never execute the model's code. The test double represents an already
committed SQLite native proposal and the actual product reviewers reread
temporary original project files. Separate CLI tests prove that a generate
request cannot begin before BOTH operator approvals and that public stdout
remains free of original source text even on post-commit failure.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_native_proposal_custody as custody,
    desktop_native_proposal_cli as cli,
    desktop_native_code_cli as code_cli,
    desktop_patch_bundle as bundle,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
)

MODEL = "a"*64
JOB = "b"*64
SESSION = "s_native_source_owner123"


def new_proposal():
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [
            {"path": "src/new.py", "content": "def helper():\n    return 42\n"},
        ],
    }, ensure_ascii=False, sort_keys=True)


def native_request(*, root, action="generate"):
    return {
        "schema": code_cli.SCHEMA,
        "action": action,
        "project_root": str(root),
        "model_root": "/private/installed-model",
        "state_dir": "/private/jeeves-state",
        "tenant": "local", "subject": "operator",
        "goal": "Generate one original helper source module",
        "format": "new-files",
        "maximum_attempts": 1,
        "source_paths": [],
        "source_context_sha256": None,
        "job_sha256": JOB if action == "generate" else None,
        "context_tokens": 4096, "max_output_tokens": 1024,
        "threads": 4, "gpu_layers": 0,
        "inference_ms": 90000,
        "capacity_budget_bytes": 8000000000,
    }


def envelope(*, root, target, action="generate-save",
             sha=None, file_sha=None, file_bytes=None,
             recheck=False):
    return {
        "schema": cli.SCHEMA,
        "action": action,
        "project_root": str(root),
        "target": str(target),
        "native_request": (
            native_request(root=root) if action == "generate-save" else None
        ),
        "expected_job_sha256": sha or JOB,
        "expected_file_sha256": file_sha,
        "expected_file_bytes": file_bytes,
        "recheck_original_source": recheck,
    }


class EscrowAdmissionTests(unittest.TestCase):
    def test_strict_cli_parser_rejects_extra_authority_and_mode_confusion(self):
        accepted = envelope(
            root="/private/workspace",
            target="/private/storage/result.source.json",
        )
        self.assertEqual(
            cli.parse_escrow_request(json.dumps(accepted).encode())["action"],
            "generate-save",
        )
        bads = (
            {},
            dict(accepted, run_shell=True),
            dict(accepted, action="execute-source"),
            dict(accepted, action=[]),
            dict(accepted, project_root="../bad"),
            dict(accepted, target="/tmp/bad/../here.source.json"),
            dict(accepted, target="relative/file.source.json"),
            dict(accepted, target="/private/workspace/inside.source.json"),
            dict(accepted, target="/private/storage/not-source.sh"),
            dict(accepted, expected_job_sha256="x"),
            dict(accepted, expected_file_sha256="a"*64),
            dict(accepted, expected_file_bytes=16),
            dict(accepted, recheck_original_source=True),
            dict(accepted, native_request=None),
            dict(accepted, native_request={"schema": "bogus"}),
            dict(accepted, native_request=dict(
                accepted["native_request"], goal="unexpected task",
                job_sha256=None,
            )),
        )
        for case_id, item in enumerate(bads):
            with self.subTest(case_id=case_id, value=repr(item)[:120]), self.assertRaises(
                (cli.NativeProposalEscrowCLIHold, ValueError),
            ):
                cli.parse_escrow_request(json.dumps(item).encode())

    def test_duplicate_nonfinite_input_is_not_parsed_as_approved(self):
        for raw in (
            b"{}", b"[]",
            b'{"action":"generate-save","action":"verify"}',
            b'{"schema":NaN}', b"\xff",
            b"x"*(cli.MAX_INPUT_BYTES + 1),
        ):
            with self.subTest(raw=raw[:30]), self.assertRaises(
                cli.NativeProposalEscrowCLIHold,
            ):
                cli.parse_escrow_request(raw)


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Cold proposal/source custody requires POSIX/WSL2",
)
class PrivateOriginalNativeSourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="jeeves-source-escrow-")
        self.addCleanup(temp.cleanup)
        self.top = Path(temp.name)
        self.root = self.top / "project"
        self.root.mkdir(mode=0o700)
        (self.root / "src").mkdir(mode=0o700)
        self.private = self.top / "private"
        self.private.mkdir(mode=0o700)
        self.target = self.private / "result.source.json"
        self.secret = "def helper():\n    return 42\n"

        def allow_test_root(value):
            return os.open(
                value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        # Shared /tmp is not an allowed production ancestry; only the
        # original fixture root/source/escrow boundary is loosened.
        for module in (workspace, edits, bundle):
            p = mock.patch.object(
                module, "_open_root", side_effect=allow_test_root,
            )
            p.start()
            self.addCleanup(p.stop)
        for module in (custody, cli):
            p = mock.patch.object(
                module, "_pinned_private_directory",
                side_effect=lambda path: allow_test_root(path.parent),
            )
            p.start()
            self.addCleanup(p.stop)

    def model_result(self, *, proposal=None):
        proposal = proposal or new_proposal()
        plan = bundle.review_patch_bundle(self.root, new_files=proposal)
        return {
            "schema": code_cli.RESULT_SCHEMA,
            "action": "generate",
            "status": "review-required",
            "job_sha256": JOB,
            "source_context_sha256": None,
            "native_model_sha256": MODEL,
            "durable_session_id": SESSION,
            "native_source": {
                "status": "review-required",
                "model_sha256": MODEL,
                "session_id": SESSION,
                "source_manifest_sha256": plan.manifest_sha256,
                "source_patch_sha256": plan.patch_sha256,
                "operator_source_context_sha256": None,
                "attempt_count": 1,
            },
            "source_receipt_verified": True,
            "operator_patch_review_required": True,
            "private_proposal_emitted": True,
            "private_proposal": proposal,
            "source_files_modified": False,
            "git_commands_executed": False,
            "model_granted_filesystem_tools": False,
            "device_qualified": False,
            "release_certified": False,
        }

    def store(self, result=None, **changed):
        return custody.publish_private_proposal(
            result or self.model_result(), self.root, self.target,
            expected_job_sha256=JOB,
            approve_private_storage=True, **changed,
        )

    def inspect(self, saved, *, recheck=False):
        return custody.verify_private_proposal(
            self.target, project_root=str(self.root),
            expected_file_sha256=saved["private_file_sha256"],
            expected_file_bytes=saved["private_file_bytes"],
            expected_job_sha256=JOB,
            recheck_original_source=recheck,
        )

    def test_private_escrow_exact_generated_source_and_cold_reopen(self):
        with (
            mock.patch("subprocess.Popen") as process,
            mock.patch("subprocess.run") as shell,
        ):
            saved = self.store()
            twice = self.inspect(saved, recheck=False)
            fresh = self.inspect(saved, recheck=True)
        self.assertEqual(saved["status"], "private-reviewed-native-source-saved")
        self.assertEqual(saved["proposal_bytes"], len(new_proposal().encode()))
        self.assertEqual(saved["proposal_sha256"],
                         sha256(new_proposal().encode()).hexdigest())
        self.assertEqual(saved["model_sha256"], MODEL)
        self.assertEqual(saved["session_id"], SESSION)
        self.assertEqual(saved["job_sha256"], JOB)
        self.assertFalse(saved["private_source_contents_disclosed"])
        self.assertFalse(saved["generated_code_executed"])
        self.assertFalse(saved["original_checkout_modified"])
        self.assertFalse(saved["release_certified"])
        self.assertEqual(twice["status"], "private-native-source-cold-verified")
        self.assertEqual(fresh["status"],
                         "private-native-source-and-original-reverified")
        self.assertEqual(fresh["source_patch_sha256"],
                         saved["source_patch_sha256"])
        self.assertTrue(self.target.exists())
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.assertNotIn(self.secret, repr(saved))
        self.assertFalse((self.root / "src/new.py").exists())
        private_json = json.loads(self.target.read_text())
        self.assertEqual(private_json["proposal"], new_proposal())
        self.assertEqual(private_json["model_sha256"], MODEL)
        self.assertEqual(private_json["job_sha256"], JOB)
        process.assert_not_called()
        shell.assert_not_called()

    def test_explicit_storage_grant_required(self):
        with self.assertRaises(custody.PrivateNativeProposalHold):
            custody.publish_private_proposal(
                self.model_result(), self.root, self.target,
                expected_job_sha256=JOB, approve_private_storage=False,
            )
        self.assertFalse(self.target.exists())

    def test_existing_destination_never_overwritten_or_reissued(self):
        first = self.store()
        payload = self.target.read_bytes()
        with self.assertRaises(FileExistsError):
            self.store()
        self.assertEqual(self.target.read_bytes(), payload)
        self.assertEqual(self.inspect(first)["proposal_sha256"],
                         first["proposal_sha256"])

    def test_wrong_full_original_job_sha_is_refused_before_writing(self):
        with self.assertRaises(custody.PrivateNativeProposalHold):
            custody.publish_private_proposal(
                self.model_result(), self.root, self.target,
                expected_job_sha256="f"*64, approve_private_storage=True,
            )
        self.assertFalse(self.target.exists())

    def test_model_replay_or_missing_authoritative_result_cannot_be_saved(self):
        originals = self.model_result()
        for change in (
            {"status": "held-exhausted"},
            {"private_proposal_emitted": False},
            {"model_granted_filesystem_tools": True},
            {"release_certified": True},
            {"source_receipt_verified": False},
            {"native_source": dict(originals["native_source"],
                                   source_patch_sha256="f"*64)},
        ):
            with self.subTest(change=change), self.assertRaises(
                custody.PrivateNativeProposalHold,
            ):
                self.store({**originals, **change})
        self.assertFalse(self.target.exists())

    def test_untrusted_generated_source_syntax_blocks_escrow(self):
        malformed = json.dumps({
            "schema": workspace.SCHEMA,
            "files": [{"path": "src/new.py", "content": "def invalid(:\n"}],
        })
        fake = self.model_result()
        fake["private_proposal"] = malformed
        with self.assertRaises(custody.PrivateNativeProposalHold):
            self.store(fake)
        self.assertFalse(self.target.exists())

    def test_cold_tamper_bytes_and_unsafe_hardlink_are_denied(self):
        saved = self.store()
        self.target.write_text("{}", encoding="utf-8")
        with self.assertRaises(custody.PrivateNativeProposalHold):
            self.inspect(saved)
        self.target.unlink()
        self.store()
        alias = self.private / "alias.source.json"
        os.link(self.target, alias)
        with self.assertRaises(custody.PrivateNativeProposalHold):
            self.inspect(saved)
        alias.unlink()
        os.chmod(self.target, 0o644)
        with self.assertRaises(custody.PrivateNativeProposalHold):
            self.inspect(saved)

    def test_original_new_destination_collision_holds_cold_source_recheck(self):
        saved = self.store()
        (self.root / "src/new.py").write_text(
            "separately created by operator", encoding="utf-8",
        )
        self.assertEqual(
            self.inspect(saved, recheck=False)["status"],
            "private-native-source-cold-verified",
        )
        with self.assertRaises(custody.PrivateNativeProposalHold):
            self.inspect(saved, recheck=True)
        self.assertEqual(
            (self.root / "src/new.py").read_text(),
            "separately created by operator",
        )

    def test_private_symlink_target_and_noncanonical_name_never_followed(self):
        file = self.private / "owner"
        file.write_text("unrelated owner document", encoding="utf-8")
        self.target.symlink_to(file)
        with self.assertRaises((OSError, custody.PrivateNativeProposalHold)):
            self.store()
        self.assertEqual(file.read_text(), "unrelated owner document")
        self.target.unlink()
        for target in (
            self.root / "inside.source.json",
            self.private / "../outside.source.json",
            self.private / ".hidden.source.json",
            self.private / "control.sh",
            Path("relative.source.json"),
        ):
            with self.subTest(target=str(target)), self.assertRaises(
                (OSError, custody.PrivateNativeProposalHold),
            ):
                custody.publish_private_proposal(
                    self.model_result(), self.root, target,
                    expected_job_sha256=JOB, approve_private_storage=True,
                )

    def test_failure_after_source_publication_removes_only_own_file(self):
        data = self.model_result()
        with mock.patch.object(
            custody, "revalidate_live_sources",
            side_effect=RuntimeError("simulated changed project"),
        ):
            with self.assertRaises(RuntimeError):
                self.store(data)
        self.assertFalse(self.target.exists())


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Strict private CLI custody requires POSIX/WSL2",
)
class NativeEscrowTerminalTests(PrivateOriginalNativeSourceTests):
    def test_both_separate_cli_grants_required_before_any_model_start(self):
        req = envelope(root=self.root, target=self.target)
        count = []
        for flags in (
            (False, False), (True, False), (False, True),
        ):
            with self.subTest(flags=flags), self.assertRaises(
                cli.NativeProposalEscrowCLIHold,
            ):
                cli.execute_escrow_request(
                    req, approve_native=flags[0],
                    approve_private_storage=flags[1],
                    bridge_factory=lambda cfg: count.append(cfg),
                )
        self.assertEqual(count, [])
        self.assertFalse(self.target.exists())

    def test_private_destination_preflight_prevents_model_if_file_exists(self):
        self.target.write_text("already owned", encoding="utf-8")
        calls = []
        with self.assertRaises(cli.NativeProposalEscrowCLIHold):
            cli.execute_escrow_request(
                envelope(root=self.root, target=self.target),
                approve_native=True, approve_private_storage=True,
                bridge_factory=lambda cfg: calls.append(cfg),
            )
        self.assertEqual(calls, [])
        self.assertEqual(self.target.read_text(), "already owned")

    def test_private_delivery_never_prints_model_source(self):
        req = envelope(root=self.root, target=self.target)
        fake = self.model_result()
        observed = []
        def generate(native_req, **kwargs):
            observed.append((native_req, kwargs))
            return fake
        with mock.patch.object(cli, "execute_native_request", side_effect=generate):
            receipt = cli.execute_escrow_request(
                req, approve_native=True, approve_private_storage=True,
            )
        self.assertEqual(
            receipt["status"],
            "native-proposal-saved-owner-private-no-source-stdout",
        )
        self.assertFalse(receipt["source_contents_in_stdout"])
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0][1]["approve_native"])
        self.assertTrue(observed[0][1]["emit_private_proposal"])
        self.assertNotIn("def helper", repr(receipt))
        self.assertTrue(self.target.exists())
        self.assertEqual(json.loads(self.target.read_text())["proposal"],
                         new_proposal())

    def test_private_cold_verify_uses_no_model_and_optional_source_check(self):
        saved = self.store()
        req = envelope(
            root=self.root, target=self.target,
            action="verify", file_sha=saved["private_file_sha256"],
            file_bytes=saved["private_file_bytes"], recheck=True,
        )
        with mock.patch.object(
            cli, "execute_native_request",
            side_effect=AssertionError("verify started a new GGUF"),
        ):
            result = cli.execute_escrow_request(req)
        self.assertEqual(result["status"], "saved-native-proposal-verified-no-inference")
        self.assertFalse(result["source_contents_in_stdout"])
        self.assertFalse(result["git_commands_executed"])
        self.assertEqual(result["private_source"]["source_patch_sha256"],
                         saved["source_patch_sha256"])

    def test_missing_model_or_escrow_flags_on_verify_refused(self):
        saved = self.store()
        req = envelope(
            root=self.root, target=self.target, action="verify",
            file_sha=saved["private_file_sha256"],
            file_bytes=saved["private_file_bytes"],
        )
        for flags in ((True, False), (False, True), (True, True)):
            with self.subTest(flags=flags), self.assertRaises(
                cli.NativeProposalEscrowCLIHold,
            ):
                cli.execute_escrow_request(
                    req, approve_native=flags[0],
                    approve_private_storage=flags[1],
                )

    def test_native_repair_hold_writes_no_private_source(self):
        raw = envelope(root=self.root, target=self.target)
        held = self.model_result()
        held.pop("private_proposal")
        held["status"] = "held-exhausted"
        held["private_proposal_emitted"] = False
        with mock.patch.object(cli, "execute_native_request", return_value=held):
            public = cli.execute_escrow_request(
                raw, approve_native=True, approve_private_storage=True,
            )
        self.assertEqual(public["status"], "native-source-held-no-private-file")
        self.assertFalse(self.target.exists())
        self.assertNotIn("def helper", repr(public))

    def test_postcommit_storage_error_preserves_sqlite_recovery_id(self):
        raw = envelope(root=self.root, target=self.target)
        fake = self.model_result()
        with (
            mock.patch.object(cli, "execute_native_request", return_value=fake),
            mock.patch.object(
                cli, "publish_private_proposal",
                side_effect=OSError("private source directory disappeared"),
            ),
        ):
            public = cli.execute_escrow_request(
                raw, approve_native=True, approve_private_storage=True,
            )
        self.assertEqual(public["status"],
                         "native-committed-private-publication-held")
        self.assertEqual(public["native_source"]["durable_session_id"], SESSION)
        self.assertTrue(public["native_source"]["manual_sqlite_inspection_required"])
        self.assertTrue(public["native_source"]["native_effect_must_not_be_reissued"])
        self.assertNotIn("private source directory", repr(public))
        self.assertFalse(self.target.exists())

    def test_main_stdin_stdout_never_exposes_source(self):
        raw = envelope(root=self.root, target=self.target)
        fake = self.model_result()
        out = StringIO()
        errors = StringIO()
        with mock.patch.object(cli, "execute_native_request", return_value=fake):
            code = cli.main(
                ["--approve-native-generation", "--approve-private-storage"],
                source=BytesIO(json.dumps(raw).encode()),
                output=out, errors=errors,
            )
        self.assertEqual(code, 0)
        self.assertEqual(errors.getvalue(), "")
        data = json.loads(out.getvalue())
        self.assertEqual(data["schema"], cli.RESULT_SCHEMA)
        self.assertFalse(data["source_contents_in_stdout"])
        self.assertNotIn("def helper", out.getvalue())
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertTrue(self.target.exists())

    def test_malformed_stdin_error_redacts_task_and_project(self):
        raw = envelope(root=self.root, target=self.target)
        raw["unexpected_model_permission"] = "private privileged tool"
        out = StringIO()
        err = StringIO()
        code = cli.main(
            ["--approve-native-generation", "--approve-private-storage"],
            source=BytesIO(json.dumps(raw).encode()),
            output=out, errors=err,
        )
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn(str(self.root), err.getvalue())
        self.assertNotIn("privileged", err.getvalue())
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
