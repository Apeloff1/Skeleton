import sqlite3
from skeleton.ai.webcrawler.migrations import migrate
from skeleton.ai.webcrawler.research_learning import ResearchLearningStore
from skeleton.ai.webcrawler.action_learning import ActionEconomics
from skeleton.ai.webcrawler.calibration import calibration_report
def test_empirical_learning_state_round_trips_and_calibrates():
 db=sqlite3.connect(":memory:");migrate(db);s=ResearchLearningStore(db)
 row=ActionEconomics("archive",10,8,.2,1.5);s.put_action(row);assert s.get_action("archive")==row
 s.record_outcome(claim_id="a",predicted=.8,actual=1,resolved_at=1)
 s.record_outcome(claim_id="b",predicted=.2,actual=0,resolved_at=2)
 vals=s.calibration_rows();r=calibration_report([x[0] for x in vals],[x[1] for x in vals])
 assert r.count==2 and r.brier<.1
