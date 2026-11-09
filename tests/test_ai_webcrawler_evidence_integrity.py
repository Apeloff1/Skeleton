from skeleton.ai.webcrawler.calibration import calibration_report
from skeleton.ai.webcrawler.evidence_revision import revision_receipt
from skeleton.ai.webcrawler.citation_lineage import extract_citation_edges,citation_dependence
from skeleton.ai.webcrawler.counterfactual import leave_one_out_influence
from skeleton.ai.webcrawler.research import EvidenceObservation,EvidenceSet,ResearchQuery
def o(i,url,text,pol=1):
 return EvidenceObservation(i,i,url,url.split("/")[2],100,"",text,1,.9,pol,(2000,))
def test_citation_lineage_finds_known_evidence_dependency():
 a=o("a","https://a.example/a","See https://b.example/b for evidence");b=o("b","https://b.example/b","primary evidence")
 e=extract_citation_edges((a,b));assert citation_dependence((a,b),e)==(("a","b"),)
def test_calibration_report_perfect_predictions_are_zero_error():
 r=calibration_report((0,1,1,0),(0,1,1,0));assert r.brier==0 and r.ece==0
def test_revision_receipt_is_deterministic_and_records_delta():
 a=revision_receipt("q",("a","b"),("b","c"),reason="new evidence",recorded_at=10)
 b=revision_receipt("q",("b","a"),("c","b"),reason="new evidence",recorded_at=10)
 assert a==b and a.added==("c",) and a.removed==("a",)
def test_counterfactual_influence_restores_evidence_set():
 e=EvidenceSet(ResearchQuery("alpha",required_sources=1));a=o("a","https://a.example/a","alpha");b=o("b","https://b.example/b","alpha")
 e.observations={a.observation_id:a,b.observation_id:b};before=dict(e.observations)
 rows=leave_one_out_influence(e,now=100)
 assert len(rows)==2 and e.observations==before
