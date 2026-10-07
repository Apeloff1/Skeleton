import unittest
from skeleton.ai.model_runtime.vocabulary_governance import ModelRuntimeError, VocabularyManifest
class TestVocabulary(unittest.TestCase):
    def test_contiguous_canonical_ids(self):
        vocab=VocabularyManifest("tok","v1",(("a",0),("b",1)),{"eos":1})
        self.assertEqual(len(vocab.digest),64)
        with self.assertRaises(ModelRuntimeError): VocabularyManifest("tok","v1",(("a",1),),{})
if __name__=="__main__": unittest.main()
