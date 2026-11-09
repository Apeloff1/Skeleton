import unittest
from skeleton.ai.multimodal.video_sampling import VideoArtifact, sample_video
D="a"*64

class TestVideoSampling(unittest.TestCase):
    def test_sampling_is_deterministic_and_spans_video(self):
        video=VideoArtifact("v",D,10000,10,D,D)
        self.assertEqual(sample_video(video,3),(0,4,9))
        self.assertEqual(sample_video(video,1),(0,))

if __name__=="__main__": unittest.main()
