from __future__ import annotations
import unittest
from skeleton.eval.vertical_suite import HandoffPacket, MultiAgentEngineeringFixture, MultiAgentTask, VerticalSuiteError

class VS004MultiAgentEngineeringTests(unittest.TestCase):
    def test_conflict_domains_are_detected_before_commit(self):
        task=MultiAgentTask("ma-1",{"builder":("a.py","shared.py"),"reviewer":("shared.py","b.py")})
        conflicts=MultiAgentEngineeringFixture().conflicts(task)
        self.assertEqual(conflicts[0].overlapping_paths,("shared.py",))

    def test_handoff_cannot_amplify_sender_authority(self):
        task=MultiAgentTask("ma-1",{"builder":("a.py",),"reviewer":("b.py",)})
        packet=HandoffPacket("builder","reviewer","ma-1",("artifact:patch",),("evidence:test",),("b.py",))
        with self.assertRaisesRegex(VerticalSuiteError,"amplifies"):
            MultiAgentEngineeringFixture().validate_handoff(task,packet)

    def test_bounded_handoff_preserves_evidence(self):
        task=MultiAgentTask("ma-1",{"builder":("a.py",),"reviewer":("b.py",)})
        packet=HandoffPacket("builder","reviewer","ma-1",("artifact:patch",),("evidence:test",),("a.py",))
        MultiAgentEngineeringFixture().validate_handoff(task,packet)

if __name__=="__main__": unittest.main()
