from skeleton.ai.webcrawler.value_of_information import ResearchAction,rank_actions
from skeleton.ai.webcrawler.sequential_evidence import sequential_bernoulli
from skeleton.ai.webcrawler.source_quality import update_source_quality,conservative_quality
def test_information_value_prefers_high_gain_low_cost_action():
 rows=rank_actions((ResearchAction("cheap",.7,.9,.1),ResearchAction("expensive",.8,.9,1.0)))
 assert rows[0].action_id=="cheap"
def test_sequential_evidence_can_continue_then_accept():
 assert sequential_bernoulli(1,0).action=="continue"
 assert sequential_bernoulli(20,1).action=="accept-high"
def test_source_quality_posterior_learns_resolved_outcomes():
 p=update_source_quality("source",correct=9,incorrect=1)
 assert p.mean>0.8 and 0<conservative_quality(p)<p.mean
