import unittest
from skeleton.ai.multimodal.speech_synthesis import MultimodalContractError, SpeechSynthesisRequest
D="a"*64

class TestSpeechSynthesis(unittest.TestCase):
    def test_voice_rights_and_output_format_are_bound(self):
        req=SpeechSynthesisRequest("r",D,"voice",D,"wav",5000)
        self.assertEqual(len(req.digest),64)
        with self.assertRaises(MultimodalContractError):
            SpeechSynthesisRequest("r",D,"voice",D,"exe",5000)

if __name__=="__main__": unittest.main()
