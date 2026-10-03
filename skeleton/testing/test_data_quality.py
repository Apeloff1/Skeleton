from skeleton.data.quality import *
def test_critical_failure_and_missing_observation_block():
 e=DataQualityEngine([DataQualityRule("r","coverage","gte",1.0,True)]); a=e.evaluate(dataset_id="d",version=1,observations=[QualityObservation("coverage",.9,10)]); b=e.evaluate(dataset_id="d",version=1,observations=[]); assert not a.promotion_allowed and a.observations[0].value==.9 and not b.promotion_allowed
