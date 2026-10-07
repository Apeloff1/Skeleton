from dataclasses import dataclass
from skeleton.ai.webcrawler.retrieval_bridge import CanonicalRetrievalBridge
from skeleton.ai.webcrawler.governance import PromotionDecision
from skeleton.ai.webcrawler.core import CrawlDocument
@dataclass
class Chunk:chunk_id:str;text:str;start:int;end:int
class Chunker:
 def chunk(self,*a):return [Chunk("c","text",0,4)]
class Index:
 revision=0
 def add(self,*a):self.revision+=1
class Entry:
 def __init__(self,i):self.entry_id=i
class Ledger:
 def __init__(self):self.n=0
 def record(self,**k):self.n+=1;return Entry(str(self.n))
def test_duplicate_delivery_returns_same_receipt_without_duplicate_provenance():
 i=Index();l=Ledger();b=CanonicalRetrievalBridge(i,l,Chunker())
 d=CrawlDocument("https://a/x","https://a/x","","text","text/plain","h",1,.9,{"schema":"p"},())
 p=PromotionDecision("p","h","promote",(),1,.9,"p",2,2)
 a=b.ingest(d,p);z=b.ingest(d,p)
 assert a==z and i.revision==1 and l.n==1
