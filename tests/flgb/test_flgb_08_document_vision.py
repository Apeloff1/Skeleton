import unittest
from skeleton.ai.multimodal.document_vision import DocumentPage, MultimodalContractError, validate_document_pages
D="a"*64

class TestDocumentVision(unittest.TestCase):
    def test_pages_are_single_document_and_contiguous(self):
        pages=(DocumentPage("d",1,D,D,D),DocumentPage("d",0,D,D,D))
        self.assertEqual([p.page_index for p in validate_document_pages(pages)],[0,1])
        with self.assertRaises(MultimodalContractError):
            validate_document_pages((DocumentPage("d",0,D,D,D),DocumentPage("d",2,D,D,D)))

if __name__=="__main__": unittest.main()
