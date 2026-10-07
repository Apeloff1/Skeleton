import unittest
from skeleton.inference.stream_decoder import FLGBInferenceError, StreamDecoder
class TestStreamDecoder(unittest.TestCase):
    def test_contiguous_jsonl(self):
        decoder = StreamDecoder(max_events=2)
        events = decoder.feed(b'{"sequence":0,"kind":"text","payload":"x"}\n{"sequence":1,"kind":"final","payload":{}}\n')
        self.assertEqual([e["sequence"] for e in events], [0, 1])
        with self.assertRaises(FLGBInferenceError):
            StreamDecoder().feed(b'{"sequence":1,"kind":"text","payload":"x"}\n')
if __name__ == "__main__": unittest.main()
