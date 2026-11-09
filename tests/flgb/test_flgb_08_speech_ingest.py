import unittest
from skeleton.ai.multimodal.speech_ingest import MultimodalContractError, SpeechArtifact
D="a"*64

class TestSpeechIngest(unittest.TestCase):
    def test_audio_bounds_and_consent_are_explicit(self):
        audio=SpeechArtifact("a",D,"audio/wav",1000,48000,2,D,D)
        self.assertEqual(len(audio.digest),64)
        with self.assertRaises(MultimodalContractError):
            SpeechArtifact("a",D,"audio/wav",1000,48000,0,D,D)

if __name__=="__main__": unittest.main()
