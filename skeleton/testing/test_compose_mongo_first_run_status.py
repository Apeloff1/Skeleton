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

    def test_untrusted_mapping_objects_are_not_executed(self):
        class HostileMapping(dict):
            def get(self, key, default=None):
                raise AssertionError("untrusted mapping callback executed")
        self.assertFalse(summarize_observation(HostileMapping(self.valid()))["observation_valid"])

    def test_unbounded_or_oversized_observations_fail_closed(self):
        payload = self.valid()
        payload.update({f"extra_{i}": i for i in range(40)})
        self.assertFalse(summarize_observation(payload)["observation_valid"])
        payload = self.valid()
        payload["code"] = COMPLETE_CODE + "x" * 200
        self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_schema_object_cannot_execute_equality_callback(self):
        class HostileSchema:
            def __eq__(self, other):
                raise AssertionError("untrusted schema equality executed")
        payload = self.valid()
        payload["schema_version"] = HostileSchema()
        self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_non_string_mapping_key_denied_without_callback(self):
        class HostileKey:
            def __hash__(self):
                return 42
            def __eq__(self, other):
                raise AssertionError("untrusted key equality executed")
        payload = self.valid()
        payload[HostileKey()] = "unused"
        self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_missing_or_malformed_inputs_fail_closed(self):
        for payload in (None, [], {}, {"schema_version": SCHEMA}, "ready"):
            with self.subTest(payload=payload):
                self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_spoofed_activation_flag_denied(self):
        payload = self.valid()
        payload["guarded_local_ai_ready"] = True
        self.assertFalse(summarize_observation(payload)["observation_valid"])

    def test_contradictory_activation_evidence_denied(self):
        for field in ("activation_permitted", "independent_reviewer_verified",
                      "canonical_writer_inventory_verified",
                      "activated_model_tokenizer_verified"):
            with self.subTest(field=field):
                payload = self.valid()
                payload[field] = True
                status = summarize_observation(payload)
                self.assertFalse(status["observation_valid"])
                self.assertFalse(status["mongo_observation_complete"])
                self.assertFalse(status["activation_permitted"])

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
