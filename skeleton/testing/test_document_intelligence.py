import pytest
from skeleton.data.document_intelligence import *
def test_document_evidence_preserves_location_and_no_instruction_authority():
 l=DocumentEvidenceLedger(); l.register(Document("d","a"*64,2,"external-untrusted")); e=l.add_region(DocumentRegion("r","d",2,(.1,.2,.8,.9),"ignore prior","ocr",.7)); assert e.page==2 and e.bbox==(.1,.2,.8,.9) and e.instruction_authority is False
def test_unregistered_document_fails():
 with pytest.raises(DocumentEvidenceError): DocumentEvidenceLedger().add_region(DocumentRegion("r","x",1,(0,0,1,1),"x","vision",.5))
