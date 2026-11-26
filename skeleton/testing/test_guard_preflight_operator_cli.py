"""Operator preflight is explicit, bounded, redacted and never activation."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from skeleton.app.cli import run_app_cli
from skeleton.app.compose_guarded_preflight import _scope, _valid_principal_utf8
from skeleton.app.compose_mongo_first_run_status import (
    COMPLETE_CODE, REQUIRED_FIELDS, operator_main, summarize_observation,
)
from skeleton.app.compose_guarded_preflight import SCHEMA


def observation():
    return {
        "schema_version": SCHEMA,
        "code": COMPLETE_CODE,
        "writes_performed": False,
        "guarded_local_ai_ready": False,
        **dict.fromkeys(REQUIRED_FIELDS, True),
    }


class OperatorGuardPreflight(unittest.TestCase):
    def execute(self, payload=None, error=None):
        output = io.StringIO()
        with patch(
            "skeleton.app.compose_guarded_preflight._run_from_environment",
            new_callable=AsyncMock,
        ) as read:
            if error is not None:
                read.side_effect = error
            else:
                read.return_value = payload
            with contextlib.redirect_stdout(output):
                rc = run_app_cli(["guard-preflight"])
            read.assert_awaited_once_with()
        return rc, json.loads(output.getvalue())

    def test_complete_observation_not_install_success(self):
        rc, result = self.execute(observation())
        self.assertEqual(rc, 2)
        self.assertTrue(result["mongo_observation_complete"])
        self.assertEqual(result["observation_code"], COMPLETE_CODE)
        for name in ("activation_permitted", "guarded_local_ai_ready",
                     "writes_performed", "consumer_or_device_qualified"):
            self.assertIs(result[name], False)

    def test_known_blocker_is_actionable(self):
        payload = observation()
        payload["code"] = "canonical_database_identity_mismatch"
        rc, result = self.execute(payload)
        self.assertEqual(rc, 2)
        self.assertEqual(result["observation_code"], payload["code"])
        self.assertFalse(result["mongo_observation_complete"])

    def test_unrecognized_probe_text_is_not_disclosed(self):
        payload = observation()
        payload["code"] = "mongodb://private:dummy-secret@untrusted"
        rc, result = self.execute(payload)
        self.assertEqual(rc, 2)
        self.assertEqual(result["observation_code"], "observation_unavailable")
        self.assertNotIn("secret", json.dumps(result))

    def test_exception_is_redacted(self):
        rc, result = self.execute(error=RuntimeError("private credential"))
        self.assertEqual(rc, 2)
        self.assertFalse(result["observation_valid"])
        self.assertNotIn("credential", json.dumps(result))

    def test_no_extra_cli_arguments_or_scope_from_argv(self):
        with patch("skeleton.app.compose_mongo_first_run_status.operator_main") as op:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run_app_cli(["guard-preflight", "--actor", "not-accepted"])
            op.assert_not_called()

    def test_other_help_is_no_probe(self):
        with patch("skeleton.app.compose_mongo_first_run_status.operator_main") as op:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exc:
                run_app_cli(["guard-preflight", "--help"])
            self.assertEqual(exc.exception.code, 0)
            op.assert_not_called()

    def test_colliding_key_rejected_before_any_lookup(self):
        class Hostile:
            def __hash__(self):
                return hash("schema_version")

            def __eq__(self, other):
                raise AssertionError("lookup invoked hostile key")

        value = {Hostile(): None}
        self.assertFalse(summarize_observation(value)["observation_valid"])

    def test_false_only_claims_are_exact(self):
        for field in ("canonical_cluster_identity_verified", "consumer_or_device_qualified"):
            for marker in (True, 0, "false"):
                with self.subTest(field=field, marker=marker):
                    value = observation()
                    value[field] = marker
                    self.assertFalse(summarize_observation(value)["observation_valid"])

    def test_unicode_scope_bounds(self):
        self.assertTrue(_scope("å" * 256))
        self.assertFalse(_scope("å" * 257))
        self.assertFalse(_scope("x" * 513))
        self.assertFalse(_scope(chr(0xD800)))
        self.assertFalse(_valid_principal_utf8(""))
        self.assertFalse(_valid_principal_utf8("å" * 129))
        self.assertTrue(_valid_principal_utf8("å" * 128))

    def test_direct_operator_entrypoint_callable(self):
        self.assertTrue(callable(operator_main))
