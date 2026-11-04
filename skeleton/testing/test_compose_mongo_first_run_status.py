"""First-run observation never becomes an activation permit."""
import unittest

from skeleton.app.compose_guarded_preflight import SCHEMA
from skeleton.app.compose_mongo_first_run_status import (
    COMPLETE_CODE, REQUIRED_FIELDS, summarize_observation,
)


class FirstRunObservationTests(unittest.TestCase):
    def valid(self):
        return {
            "schema_version": SCHEMA,
            "code": COMPLETE_CODE,
            "writes_performed": False,
            "guarded_local_ai_ready": False,
            **{key: True for key in REQUIRED_FIELDS},
        }

    def test_complete_observation_is_not_activation(self):
        status = summarize_observation(self.valid())
        self.assertTrue(status["mongo_observation_complete"])
        self.assertFalse(status["activation_permitted"])
        self.assertFalse(status["guarded_local_ai_ready"])

    def test_missing_or_malformed_inputs_fail_closed(self):
        for payload in (None, [], {}, {"schema_version": SCHEMA}, "ready"):
            with self.subTest(payload=payload):
                self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_spoofed_activation_flag_denied(self):
        payload = self.valid()
        payload["guarded_local_ai_ready"] = True
        self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_spoofed_write_flag_denied(self):
        payload = self.valid()
        payload["writes_performed"] = True
        self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_bool_as_integer_not_accepted(self):
        for key in REQUIRED_FIELDS:
            payload = self.valid()
            payload[key] = 1
            with self.subTest(key=key):
                self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_error_code_cannot_masquerade_as_complete_observation(self):
        for code in ("mongo_primary_probe_unavailable",
                     "canonical_actor_epoch_changed_during_preflight",
                     "mongo_preflight_deadline_exceeded", "", "unknown"):
            payload = self.valid()
            payload["code"] = code
            with self.subTest(code=code):
                status = summarize_observation(payload)
                self.assertFalse(status["mongo_observation_complete"])
                self.assertFalse(status["activation_permitted"])

    def test_missing_or_non_string_code_never_complete(self):
        for code in (None, False, 1, [], {}):
            payload = self.valid()
            payload["code"] = code
            with self.subTest(code=code):
                self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_partial_observation_never_complete(self):
        for key in REQUIRED_FIELDS:
            payload = self.valid()
            payload[key] = False
            with self.subTest(key=key):
                status = summarize_observation(payload)
                self.assertTrue(status["observation_valid"])
                self.assertFalse(status["mongo_observation_complete"])
                self.assertFalse(status["activation_permitted"])


if __name__ == "__main__":
    unittest.main()
