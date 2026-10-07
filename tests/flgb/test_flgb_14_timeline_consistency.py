import unittest
from skeleton.game.generation.timeline_consistency import TimelineEvent, timeline_conflicts
D="a"*64
class T(unittest.TestCase):
 def test_subject_overlap_detected(self):
  a=TimelineEvent("a",0,10,("hero",),D); b=TimelineEvent("b",5,12,("hero",),D)
  self.assertEqual(timeline_conflicts((a,b)),(("a","b"),))
if __name__=="__main__": unittest.main()
