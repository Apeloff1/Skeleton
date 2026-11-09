from skeleton.ai.webcrawler.information_gain import binary_entropy,expected_binary_information_gain
from skeleton.ai.webcrawler.research_controller import ControllerCandidate,choose_next_action
from skeleton.ai.webcrawler.source_quality import SourcePosterior
from skeleton.ai.webcrawler.dependence_trust import dependence_adjusted_trust
from skeleton.ai.webcrawler.research import EvidenceObservation
from skeleton.ai.webcrawler.source_dependence import DependenceEdge
def o(i,h):return EvidenceObservation(i,i,"https://"+h,h,1,"","x",1,1,1,(2000,))
def test_entropy_information_gain_is_zero_for_uninformative_test():
 assert expected_binary_information_gain(.5,sensitivity=.5,specificity=.5).gain==0
 assert expected_binary_information_gain(.5,sensitivity=.95,specificity=.95).gain>.5
def test_controller_respects_budget_and_information_value():
 rows=(ControllerCandidate("good","archive",.9,.9,.2,.1),ControllerCandidate("too-expensive","deep",.99,.99,5,.1))
 assert choose_next_action(.5,rows,budget=1).action_id=="good"
def test_dependence_adjusted_trust_does_not_multiply_copies():
 a=o("a","a.example");b=o("b","b.example");edge=DependenceEdge("a","b",1,("direct-citation",))
 p={"a.example":SourcePosterior("a.example",9,1),"b.example":SourcePosterior("b.example",8,2)}
 rows=dependence_adjusted_trust((a,b),(edge,),p)
 assert len(rows)==1 and rows[0].trust==.9
