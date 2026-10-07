import unittest
from skeleton.ai.multimodal.audio_understanding import AudioSegment, MultimodalContractError, validate_audio_segments
D="a"*64

class TestAudioUnderstanding(unittest.TestCase):
    def test_segments_cannot_escape_artifact_duration(self):
        segment=AudioSegment("s",0,1000,"speech",900000,D)
        self.assertEqual(validate_audio_segments((segment,),1000)[0],segment)
        with self.assertRaises(MultimodalContractError):
            validate_audio_segments((AudioSegment("x",0,1001,"speech",1,D),),1000)

if __name__=="__main__": unittest.main()
