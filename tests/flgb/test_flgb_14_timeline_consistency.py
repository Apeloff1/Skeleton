import unittest
from skeleton.game.generation.timeline_consistency import GenerationContractError, TimelineEvent, validate_timeline
D="a"*64
class TestTimelineConsistency(unittest.TestCase):
    def test_same_subject_overlaps_are_rejected(self):
        events=(TimelineEvent("a",0,10,"hero",D),TimelineEvent("b",10,20,"hero",D),TimelineEvent("c",5,15,"villain",D))
        self.assertEqual([e.event_id for e in validate_timeline(events)],["a","c","b"])
        with self.assertRaises(GenerationContractError):
            validate_timeline((TimelineEvent("a",0,10,"hero",D),TimelineEvent("b",9,20,"hero",D)))
if __name__=="__main__": unittest.main()
