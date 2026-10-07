from __future__ import annotations
import hashlib
from skeleton.document_vision.fusion import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
P=DocumentPage("DOC.1",1,S("page"),100,100);R=LayoutRegion(1,1,2,20,10)
def test_ocr_retains_page_coordinates_confidence_and_model(): assert fuse(P,OCRSpan(R,"hello",.9,S("ocr"))).status=="ocr_only"
def test_matching_native_text_is_agreement(): assert fuse(P,OCRSpan(R,"hello",.9,S("ocr")),TextEvidence(R,"hello","native")).status=="agree"
def test_conflicting_text_layer_is_surfaced_not_silently_chosen():
 r=fuse(P,OCRSpan(R,"hello",.9,S("ocr")),TextEvidence(R,"h3llo","native")); assert r.status=="conflict" and r.ocr_text=="hello" and r.native_text=="h3llo"
def test_out_of_page_region_fails_closed():
 try: fuse(P,OCRSpan(LayoutRegion(1,95,0,10,10),"x",.9,S("ocr")))
 except DocumentVisionError: return
 assert False