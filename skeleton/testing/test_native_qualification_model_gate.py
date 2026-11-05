"""No fixture service can enter the real-native model qualification runner."""
from __future__ import annotations
from types import SimpleNamespace
import unittest
from skeleton.ai.runtime.operational_ai.native_qualification.model_gate import require_real_service
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


class FakeFixtureService:
    actor=SimpleNamespace(tenant="tenant",user="user",model_digest="a"*64)
    def turn(self, **kwargs):
        return SimpleNamespace(text="pretend-pass")


class TestRealNativeGate(unittest.TestCase):
    def test_fixture_rejected(self):
        with self.assertRaises(QualificationError):
            require_real_service(FakeFixtureService())

    def test_missing_service_rejected(self):
        with self.assertRaises(QualificationError):
            require_real_service(None)


if __name__ == "__main__":
    unittest.main()
