"""Offline laptop runtime qualification: runtime_state; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.runtime_state import RuntimeState
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestRuntimeState(unittest.TestCase):
    def test_ordered_state_transitions(self):
        state=RuntimeState()
        phases=("install-verified","native-loaded","serving","draining","stopped")
        for i,phase in enumerate(phases):
            event=state.transition(phase,evidence_sha256=(hex(i+10)[2:]).rjust(64,"0"))
            self.assertEqual(event["sequence"],i+1)
        self.assertEqual(state.snapshot()["state"],"stopped")
        with self.assertRaises(ContractViolation):
            state.transition("serving",evidence_sha256="e"*64)
    def test_cannot_reuse_evidence_or_skip_loading(self):
        state=RuntimeState()
        state.transition("install-verified",evidence_sha256="a"*64)
        with self.assertRaises(ContractViolation):
            state.transition("native-loaded",evidence_sha256="a"*64)
        with self.assertRaises(ContractViolation):
            state.transition("serving",evidence_sha256="b"*64)

if __name__=="__main__":
    unittest.main()
