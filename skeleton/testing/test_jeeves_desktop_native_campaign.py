"""Strict source-only campaign qualifications for real GGUF+SQLite orchestration.

Real files exercise private audit bytes, hash-chain and no-clobber custody.
Only model execution and sealed native escrow are explicitly substituted with
recorded contract-shaped data. These tests DO NOT claim live model E2E.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_campaign_journal as journal,
    desktop_native_campaign as campaign,
    desktop_native_campaign_cli as cli,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli import (
    SCHEMA as NATIVE_SCHEMA, execute_native_request,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_workspace import _canonical


A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


class CampaignFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.model = self.root / "model"
        self.state = self.root / "state"
        self.journal_file = self.private / "work.jeeves-campaign.jsonl"

    def native(self, name="task one", *, attempts=1, inference_ms=1000,
               max_output_tokens=128):
        prototype = {
            "schema": NATIVE_SCHEMA, "action": "inspect",
            "project_root": str(self.project),
            "model_root": str(self.model), "state_dir": str(self.state),
            "tenant": "owner", "subject": "local",
            "goal": name, "format": "new-files",
            "maximum_attempts": attempts,
            "source_paths": [], "source_context_sha256": None,
            "job_sha256": None,
            "context_tokens": 1024, "max_output_tokens": max_output_tokens,
            "threads": 2, "gpu_layers": 0,
            "inference_ms": inference_ms,
            "capacity_budget_bytes": 1024 * 1024 * 1024,
        }
        receipt = execute_native_request(prototype)
        return {**prototype, "action": "generate",
                "job_sha256": receipt["job_sha256"]}

    def request(self, names=("one", "two"), action="inspect", **kwargs):
        tasks = []
        for index, item in enumerate(names):
            native = self.native(item + " original source")
            tasks.append({
                "task_id": item,
                "depends_on": [names[index - 1]] if index else [],
                "target": str(self.private / (item + ".source.json")),
                "expected_job_sha256": native["job_sha256"],
                "native_request": native,
            })
        request = {
            "schema": campaign.SCHEMA,
            "action": action,
            "project_root": str(self.project),
            "journal_file": str(self.journal_file),
            "manifest_sha256": None,
            "recheck_original_source": False,
            "tasks": tasks,
        }
        request.update(kwargs)
        if action != "inspect":
            preview = {**request, "action": "inspect",
                       "manifest_sha256": None,
                       "recheck_original_source": False}
            request["manifest_sha256"] = campaign.parse_campaign(
                _canonical(preview),
            )[0].manifest_sha256
        return request

    def plan(self, names=("one", "two")):
        return campaign.parse_campaign(
            _canonical(self.request(names=names)),
        )[0]

    def receipt(self, item):
        return {
            "job_sha256": item.expected_job_sha256,
            "private_file_sha256": A,
            "private_file_bytes": 128,
            "model_sha256": B,
            "session_id": "sqlite-" + item.task_id,
            "source_manifest_sha256": C,
            "source_patch_sha256": D,
        }

    def escrow(self, task):
        return {
            "status": "native-proposal-saved-owner-private-no-source-stdout",
            "source_contents_in_stdout": False,
            "original_source_modified": False,
            "generated_code_executed": False,
            "release_certified": False,
            "private_source": {
                "status": "private-reviewed-native-source-saved",
                **self.receipt(task),
            },
        }

    def mock_native(self, plan):
        values = [self.escrow(task) for task in plan.tasks]
        return (
            mock.patch.object(campaign, "execute_escrow_request", side_effect=values),
            mock.patch.object(campaign, "verify_private_proposal",
                              side_effect=lambda source, **kw:
                              self.receipt(next(task for task in plan.tasks
                                                if task.target == source))),
        )


class CampaignAdmissionTests(CampaignFixture):
    def test_readonly_campaign_inspection_rechecks_real_native_job_hashes(self):
        plan = self.plan()
        inspected = campaign.inspect_campaign(plan)
        self.assertEqual(inspected["task_count"], 2)
        self.assertEqual(inspected["total_maximum_native_attempts"], 2)
        self.assertEqual(inspected["task_receipts"][0]["task_id"], "one")
        self.assertFalse(inspected["model_started"])
        self.assertNotIn(str(self.project), json.dumps(inspected))
        self.assertNotIn("one original source", json.dumps(inspected))
        self.assertFalse(self.journal_file.exists())

    def test_original_task_mutation_is_refused_before_any_model(self):
        request = self.request()
        request["tasks"][0]["native_request"]["goal"] += " MODIFIED"
        # Structural JSON parsing cannot establish the live original file
        # and job digest. The read-only inspector is the authoritative
        # pre-model review boundary and must refuse changed task bytes.
        plan, _ = campaign.parse_campaign(_canonical(request))
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.inspect_campaign(plan)

    def test_duplicate_task_id_is_denied(self):
        req = self.request()
        req["tasks"][1]["task_id"] = "one"
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(_canonical(req))

    def test_duplicate_or_malformed_dependency_is_denied(self):
        for dependency in (["two"], ["missing"], ["one", "one"]):
            with self.subTest(dependency=dependency):
                req = self.request()
                req["tasks"][0]["depends_on"] = dependency
                with self.assertRaises(campaign.NativeCampaignHold):
                    campaign.parse_campaign(_canonical(req))

    def test_cycle_and_forward_dependency_never_start_a_model(self):
        req = self.request()
        req["tasks"][0]["depends_on"] = ["two"]
        req["tasks"][1]["depends_on"] = ["one"]
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(_canonical(req))

    def test_private_escrow_target_cannot_overlap_original_project(self):
        req = self.request()
        req["tasks"][0]["target"] = str(self.project / "candidate.source.json")
        with self.assertRaises((ValueError, campaign.NativeCampaignHold)):
            campaign.parse_campaign(_canonical(req))

    def test_private_escrow_target_must_share_approved_journal_parent(self):
        req = self.request()
        req["tasks"][0]["target"] = str(self.root / "candidate.source.json")
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(_canonical(req))

    def test_model_and_sqlite_principal_cannot_drift_between_jobs(self):
        for key, value in (("tenant", "other"), ("subject", "other"),
                           ("model_root", "/other/model"),
                           ("state_dir", "/other/state")):
            with self.subTest(key=key):
                req = self.request()
                native = req["tasks"][1]["native_request"]
                native[key] = value
                native["action"] = "inspect"
                native["job_sha256"] = None
                changed = execute_native_request(native)["job_sha256"]
                native["action"] = "generate"
                native["job_sha256"] = changed
                req["tasks"][1]["expected_job_sha256"] = changed
                with self.assertRaises(campaign.NativeCampaignHold):
                    campaign.parse_campaign(_canonical(req))

    def test_total_attempts_are_bounded_not_per_job_only(self):
        req = self.request(names=("a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"))
        for row in req["tasks"]:
            native = row["native_request"]
            native["maximum_attempts"] = 3
            native["action"], native["job_sha256"] = "inspect", None
            digest = execute_native_request(native)["job_sha256"]
            native["action"], native["job_sha256"] = "generate", digest
            row["expected_job_sha256"] = digest
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(_canonical(req))

    def test_per_campaign_wall_clock_ceiling_is_conservative(self):
        req = self.request(names=("a", "b", "c"))
        for row in req["tasks"]:
            native = row["native_request"]
            native["inference_ms"] = 500000
            native["action"], native["job_sha256"] = "inspect", None
            digest = execute_native_request(native)["job_sha256"]
            native["action"], native["job_sha256"] = "generate", digest
            row["expected_job_sha256"] = digest
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(_canonical(req))

    def test_unexpected_json_fields_and_duplicate_keys_are_denied(self):
        req = self.request()
        req["hidden_authority"] = "write"
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(_canonical(req))
        good = _canonical(self.request())
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(
                good.replace(b'"schema":', b'"schema":"forged","schema":', 1),
            )

    def test_nan_and_nonfinite_source_budgets_hold(self):
        req = _canonical(self.request())
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(
                req.replace(b'"maximum_attempts":1',
                            b'"maximum_attempts":NaN', 1),
            )

    def test_missing_explicit_digest_for_run_is_terminal(self):
        req = self.request(action="run")
        req["manifest_sha256"] = A
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.parse_campaign(_canonical(req))

    def test_inspection_must_not_carry_model_grants(self):
        req = self.request()
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign.execute_campaign_request(req, approve_native=True)

    def test_run_requires_three_independent_explicit_grants(self):
        req = self.request(action="run")
        for flags in (
            {}, {"approve_campaign": True},
            {"approve_native": True, "approve_private_storage": True},
            {"approve_campaign": True, "approve_native": True},
        ):
            with self.subTest(flags=flags):
                with self.assertRaises(campaign.NativeCampaignHold):
                    campaign.execute_campaign_request(req, **flags)
        self.assertFalse(self.journal_file.exists())

    def test_no_second_run_can_replay_an_existing_campaign(self):
        plan = self.plan()
        with journal.CampaignJournalWriter(
            str(self.journal_file), project_root=str(self.project),
            manifest_sha256=plan.manifest_sha256,
        ) as log:
            log.append("begin")
        with self.assertRaises(campaign.NativeCampaignHold):
            campaign._preflight_all(plan)

    def test_original_project_file_is_untouched_by_inspection(self):
        source = self.project / "important.py"
        source.write_text("important = 1\n")
        digest = sha256(source.read_bytes()).hexdigest()
        campaign.inspect_campaign(self.plan())
        self.assertEqual(sha256(source.read_bytes()).hexdigest(), digest)


class CampaignJournalTests(CampaignFixture):
    def write(self, *, failed=False):
        plan = self.plan()
        with journal.CampaignJournalWriter(
            str(self.journal_file), project_root=str(self.project),
            manifest_sha256=plan.manifest_sha256,
        ) as sink:
            sink.append("begin")
            for index, task in enumerate(plan.tasks):
                sink.append("attempt", task_id=task.task_id,
                            evidence={"job_sha256": task.expected_job_sha256})
                if failed and index == 1:
                    sink.append("halt", evidence={"reason": "native-uncertain"})
                    break
                sink.append("saved", task_id=task.task_id,
                            evidence=self.receipt(task))
            if not failed:
                sink.append("complete")
        return plan

    def test_reopened_private_hash_chain_proves_all_saved_native_receipts(self):
        plan = self.write()
        state = journal.inspect_campaign_journal(
            str(self.journal_file), project_root=str(self.project),
            manifest_sha256=plan.manifest_sha256,
            task_ids=("one", "two"),
        )
        self.assertEqual(state["status"], "complete-cold-audit-receipts")
        self.assertEqual(state["saved_task_count"], 2)
        self.assertTrue(state["all_tasks_completed"])
        self.assertFalse(state["automatic_native_retry_permitted"])
        self.assertEqual(self.journal_file.stat().st_mode & 0o777, 0o600)

    def test_interrupted_native_attempt_never_becomes_a_success(self):
        plan = self.write(failed=True)
        state = journal.inspect_campaign_journal(
            str(self.journal_file), project_root=str(self.project),
            manifest_sha256=plan.manifest_sha256,
            task_ids=("one", "two"),
        )
        self.assertEqual(state["status"], "uncertain-native-attempt-no-retry")
        self.assertEqual(state["uncertain_task_ids"], ("two",))
        self.assertFalse(state["all_tasks_completed"])

    def test_short_write_or_journal_truncation_is_held(self):
        plan = self.write()
        raw = self.journal_file.read_bytes()
        for changed in (raw[:-1], raw[:len(raw) // 2], b""):
            with self.subTest(size=len(changed)):
                with self.assertRaises(journal.NativeCampaignJournalHold):
                    journal.parse_campaign_journal(
                        changed, expected_manifest_sha256=plan.manifest_sha256,
                        task_ids=("one", "two"),
                    )

    def test_modified_or_reordered_receipts_fail_sha_chain(self):
        plan = self.write()
        raw = self.journal_file.read_bytes()
        changed = raw.replace(b'"event":"complete"', b'"event":"halt"', 1)
        with self.assertRaises(journal.NativeCampaignJournalHold):
            journal.parse_campaign_journal(
                changed, expected_manifest_sha256=plan.manifest_sha256,
                task_ids=("one", "two"),
            )
        frames = raw.splitlines(keepends=True)
        frames[1], frames[2] = frames[2], frames[1]
        with self.assertRaises(journal.NativeCampaignJournalHold):
            journal.parse_campaign_journal(
                b"".join(frames),
                expected_manifest_sha256=plan.manifest_sha256,
                task_ids=("one", "two"),
            )

    def test_audit_cannot_be_created_twice_or_overwrite_a_human_file(self):
        plan = self.write()
        original = self.journal_file.read_bytes()
        with self.assertRaises(FileExistsError):
            with journal.CampaignJournalWriter(
                str(self.journal_file), project_root=str(self.project),
                manifest_sha256=plan.manifest_sha256,
            ):
                pass
        self.assertEqual(self.journal_file.read_bytes(), original)

    @unittest.skipUnless(os.name == "posix", "POSIX private no-follow journal")
    def test_symlink_journal_is_rejected(self):
        plan = self.plan()
        original = self.root / "elsewhere"
        original.write_bytes(b"private data")
        self.journal_file.symlink_to(original)
        with self.assertRaises((OSError, ValueError)):
            journal.inspect_campaign_journal(
                str(self.journal_file), project_root=str(self.project),
                manifest_sha256=plan.manifest_sha256,
                task_ids=("one", "two"),
            )
        self.assertEqual(original.read_bytes(), b"private data")

    def test_unsigned_fabricated_saved_state_cannot_claim_completion(self):
        plan = self.plan()
        bad = _canonical({
            "schema": journal.SCHEMA, "sequence": 1,
            "previous_sha256": "0" * 64, "event": "complete",
            "manifest_sha256": plan.manifest_sha256,
            "task_id": None, "evidence": {}, "event_sha256": A,
        }) + b"\n"
        with self.assertRaises(journal.NativeCampaignJournalHold):
            journal.parse_campaign_journal(
                bad, expected_manifest_sha256=plan.manifest_sha256,
                task_ids=("one", "two"),
            )


class NativeCampaignExecutionTests(CampaignFixture):
    def test_two_real_sequence_shapes_with_inert_model_double(self):
        plan = self.plan()
        first, second = self.mock_native(plan)
        with first as run, second as cold:
            result = campaign.run_campaign(
                plan, approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
            self.assertEqual(
                result["status"], "all-private-source-escrows-cold-verified",
            )
            self.assertEqual(run.call_count, 2)
            self.assertEqual(cold.call_count, 4)
            self.assertEqual(
                [call.args[0]["target"] for call in run.call_args_list],
                [task.target for task in plan.tasks],
            )
        audit = journal.inspect_campaign_journal(
            str(self.journal_file), project_root=str(self.project),
            manifest_sha256=plan.manifest_sha256,
            task_ids=("one", "two"),
        )
        self.assertTrue(audit["all_tasks_completed"])
        self.assertEqual(audit["saved_task_count"], 2)

    def test_model_failure_stops_following_tasks_and_never_reissues(self):
        plan = self.plan()
        with mock.patch.object(campaign, "execute_escrow_request",
                               side_effect=RuntimeError("private source token")) as run:
            result = campaign.run_campaign(
                plan, approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
        self.assertEqual(result["status"], "native-campaign-held-no-auto-retry")
        self.assertEqual(run.call_count, 1)
        self.assertTrue(result["native_sqlite_may_have_committed"])
        self.assertNotIn("private source token", json.dumps(result))
        state = journal.inspect_campaign_journal(
            str(self.journal_file), project_root=str(self.project),
            manifest_sha256=plan.manifest_sha256,
            task_ids=("one", "two"),
        )
        self.assertEqual(state["uncertain_task_ids"], ("one",))
        self.assertFalse(state["automatic_native_retry_permitted"])

    def test_untrusted_model_receipt_does_not_allow_second_job(self):
        plan = self.plan()
        with mock.patch.object(campaign, "execute_escrow_request",
                               return_value={"status": "review-required"}) as run:
            result = campaign.run_campaign(
                plan, approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
        self.assertEqual(result["status"], "native-campaign-held-no-auto-retry")
        run.assert_called_once()
        self.assertFalse(result["source_audit"]["all_tasks_completed"])

    def test_second_job_requires_first_saved_receipt(self):
        plan = self.plan()
        values = [
            self.escrow(plan.tasks[0]),
            {"status": "native-source-held-no-private-file"},
        ]
        with mock.patch.object(campaign, "execute_escrow_request",
                               side_effect=values) as run, \
             mock.patch.object(campaign, "verify_private_proposal",
                               return_value=self.receipt(plan.tasks[0])):
            outcome = campaign.run_campaign(
                plan, approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
        self.assertEqual(run.call_count, 2)
        self.assertEqual(outcome["source_audit"]["saved_task_count"], 1)
        self.assertFalse(outcome["source_audit"]["all_tasks_completed"])

    def test_private_target_collision_blocks_before_native_calls(self):
        plan = self.plan()
        Path(plan.tasks[1].target).write_text("owned by somebody")
        with mock.patch.object(campaign, "execute_escrow_request") as model:
            with self.assertRaises((campaign.NativeCampaignHold, ValueError)):
                campaign.run_campaign(
                    plan, approve_campaign=True, approve_native=True,
                    approve_private_storage=True,
                )
            model.assert_not_called()
        self.assertFalse(self.journal_file.exists())

    def test_cold_verify_checks_all_saved_receipts_without_model(self):
        plan = self.plan()
        a, b = self.mock_native(plan)
        with a, b:
            campaign.run_campaign(
                plan, approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
        with mock.patch.object(campaign, "execute_escrow_request") as model, \
             mock.patch.object(campaign, "verify_private_proposal",
                               side_effect=lambda source, **kw:
                               self.receipt(next(task for task in plan.tasks
                                                 if task.target == source))):
            result = campaign.verify_campaign(plan)
            self.assertTrue(result["all_source_escrows_cold_verified"])
            self.assertEqual(result["cold_verified_private_source_count"], 2)
            model.assert_not_called()

    def test_drifted_escrow_source_is_not_promoted_by_cold_audit(self):
        plan = self.plan()
        a, b = self.mock_native(plan)
        with a, b:
            campaign.run_campaign(
                plan, approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
        with mock.patch.object(campaign, "verify_private_proposal",
                               return_value={"job_sha256": A}):
            with self.assertRaises(campaign.NativeCampaignHold):
                campaign.verify_campaign(plan)

    def test_successful_run_no_original_source_or_model_tokens_enter_receipt(self):
        plan = self.plan(names=("one",))
        a, b = self.mock_native(plan)
        with a, b:
            receipt = campaign.run_campaign(
                plan, approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
        text = json.dumps(receipt)
        self.assertNotIn(str(self.project), text)
        self.assertNotIn(str(self.private), text)
        self.assertNotIn("one original source", text)
        self.assertFalse(receipt["release_certified"])


class CampaignCLITests(CampaignFixture):
    def test_readonly_cli_does_not_need_a_native_process(self):
        request = self.request(names=("one",))
        output = io.StringIO()
        error = io.StringIO()
        code = cli.main([], stdin=io.BytesIO(_canonical(request)),
                        stdout=output, stderr=error)
        self.assertEqual(code, 0)
        self.assertIn("review-required-before-original-native-campaign",
                      output.getvalue())
        self.assertEqual(error.getvalue(), "")

    def test_cli_nonconsented_run_only_emits_generic_hold(self):
        request = self.request(action="run")
        output = io.StringIO()
        error = io.StringIO()
        code = cli.main([], stdin=io.BytesIO(_canonical(request)),
                        stdout=output, stderr=error)
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(
            error.getvalue(), "JEEVES_NATIVE_CAMPAIGN_HELD_NO_AUTOMATIC_RETRY\n",
        )

    def test_cli_rejects_large_input_before_source_review(self):
        output = io.StringIO()
        error = io.StringIO()
        code = cli.main(
            [], stdin=io.BytesIO(b"A" * (campaign.MAX_REQUEST_BYTES + 1)),
            stdout=output, stderr=error,
        )
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
