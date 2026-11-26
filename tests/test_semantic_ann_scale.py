from scripts.qualify_semantic_ann_scale import qualify
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy


def test_physical_shard_scale_diagnostic_reports_complete_denominator(tmp_path):
    root=tmp_path/"index";root.mkdir(mode=0o700)
    report=qualify(root,"fixture",rows=64,dimension=8,queries=3,k=3,seed=4,
        policy=DiskANNPolicy(shards=2,bands=4,bits=4,probes=5,workers=2,max_index_bytes=8*1024**2))
    assert report["rows"]==64 and len(report["rows_detail"])==3
    assert 0<=report["mean_recall_at_k"]<=1 and report["index_bytes"]>0
    assert all(x["shards_searched"]==2 for x in report["rows_detail"])
    assert report["production_scale_certified"] is False
