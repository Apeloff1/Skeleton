import unittest
from skeleton.game.generation.timeline_consistency import ContinuityContractError, TimelineEvent, validate_timeline
D="a"*64

class TestTimelineConsistency(unittest.TestCase):
    def test_causal_parent_must_finish_before_child(self):
        parent=TimelineEvent("origin",0,10,(),D)
        child=TimelineEvent("aftermath",10,20,("origin",),D)
        self.assertEqual([e.event_id for e in validate_timeline((child,parent))],["origin","aftermath"])
        with self.assertRaises(ContinuityContractError):
            validate_timeline((parent,TimelineEvent("bad",5,20,("origin",),D)))

if __name__=="__main__": unittest.main()
