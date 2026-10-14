from skeleton.ai.webcrawler.governance import PromotionDecision
from skeleton.ai.webcrawler.knowledge_bridge import CanonicalKnowledgeBridge
from skeleton.ai.webcrawler.core import CrawlDocument
class Store:
 def record(self,claim):return "id"
def doc():
 return CrawlDocument("https://a.example/x","https://a.example/x","","text","text/plain","h",1,.9,{"schema":"p"},())
def test_bridge_rejects_fabricated_uncorroborated_promotion():
 d=PromotionDecision("id","h","promote",(),1,.9,"p",1,2)
 try:CanonicalKnowledgeBridge(Store()).record_document(doc(),d)
 except ValueError as exc:assert "independent" in str(exc)
 else:raise AssertionError("uncorroborated promotion accepted")
