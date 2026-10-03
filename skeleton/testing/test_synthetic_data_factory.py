from skeleton.data.synthetic import *
def test_synthetic_origin_and_quality_gates():
 f=SyntheticDataFactory(SyntheticJob("j","g","v","a"*64,"ds")); a=f.record(record_id="a",value={"x":1},group_label="g1",parent_refs=["p"]); f.record(record_id="b",value={"x":1},group_label="g1",parent_refs=["p"]); q=f.evaluate(reference_content_digests=[a.content_digest],valid_record_ids=["a","b"],min_diversity=.8,max_memorization=.1,max_group_share=.8); assert a.origin=="synthetic" and not q.promotion_allowed and q.memorization_ratio==1.0
