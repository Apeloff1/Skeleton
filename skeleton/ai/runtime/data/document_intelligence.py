"""Document evidence preserving page/region coordinates and extraction uncertainty."""
from dataclasses import dataclass
class DocumentEvidenceError(ValueError): pass
@dataclass(frozen=True, slots=True)
class Document: document_id:str; source_digest:str; page_count:int; trust_context:str
@dataclass(frozen=True, slots=True)
class DocumentRegion: region_id:str; document_id:str; page:int; bbox:tuple[float,float,float,float]; text:str; extraction_method:str; confidence:float
@dataclass(frozen=True, slots=True)
class ExtractionEvidence: document_id:str; source_digest:str; region_id:str; page:int; bbox:tuple[float,float,float,float]; extraction_method:str; confidence:float; trust_context:str; instruction_authority:bool=False
class DocumentEvidenceLedger:
    def __init__(self): self._documents={}; self._regions={}
    def register(self,doc):
        if not doc.document_id or len(doc.source_digest)!=64 or doc.page_count<1: raise DocumentEvidenceError("invalid document")
        old=self._documents.get(doc.document_id)
        if old is not None and old!=doc: raise DocumentEvidenceError("document identity cannot be rebound")
        self._documents[doc.document_id]=doc
    def add_region(self,r):
        d=self._documents.get(r.document_id)
        if d is None: raise DocumentEvidenceError("unregistered document")
        if r.page<1 or r.page>d.page_count or r.extraction_method not in {"native_text","ocr","vision"}: raise DocumentEvidenceError("invalid extraction location/method")
        if len(r.bbox)!=4 or not all(isinstance(v,(int,float)) and 0<=float(v)<=1 for v in r.bbox): raise DocumentEvidenceError("invalid bbox")
        x0,y0,x1,y1=r.bbox
        if not (x0<x1 and y0<y1) or not 0<=float(r.confidence)<=1: raise DocumentEvidenceError("invalid region geometry/confidence")
        old=self._regions.get(r.region_id)
        if old is not None and old!=r: raise DocumentEvidenceError("region identity cannot be rebound")
        self._regions[r.region_id]=r
        return ExtractionEvidence(d.document_id,d.source_digest,r.region_id,r.page,r.bbox,r.extraction_method,float(r.confidence),d.trust_context,False)
