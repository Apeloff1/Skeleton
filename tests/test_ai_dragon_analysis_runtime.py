"""Durable analysis runtime regressions."""
import sqlite3,pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import WorkerCapability
from skeleton.ai.webcrawler.dragon_analysis_runtime import DragonAnalysisRuntime


def caps():
    return tuple(WorkerCapability(x,f"worker.{x.value}","v1",True) for x in AnalysisLayer)


def test_runtime_dispatches_strictly_in_dependency_order():
    rt=DragonAnalysisRuntime(sqlite3.connect(":memory:")); cp=rt.create("u","r",now=1,authorized=True)
    d=rt.next_dispatch("u","r",caps(),authorized=True)
    assert d.layer is AnalysisLayer.SOURCE_INTEGRITY
    receipt=LayerReceipt(d.layer,d.input_fingerprints,"a"*64,1,True,False)
    cp=rt.commit_receipt("u","r",receipt,now=2,expected_revision=cp.revision,authorized=True)
    assert rt.next_dispatch("u","r",caps(),authorized=True).layer is AnalysisLayer.TEMPORAL_SEGMENTATION


def test_stale_checkpoint_cannot_commit():
    rt=DragonAnalysisRuntime(sqlite3.connect(":memory:")); cp=rt.create("u","r",now=1,authorized=True)
    d=rt.next_dispatch("u","r",caps(),authorized=True)
    rt.commit_receipt("u","r",LayerReceipt(d.layer,(),"a"*64,1,True),now=2,
        expected_revision=cp.revision,authorized=True)
    with pytest.raises(RuntimeError,match="stale"):
        rt.commit_receipt("u","r",LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True),
            now=3,expected_revision=cp.revision,authorized=True)


def test_cancellation_is_durable_and_stops_dispatch():
    rt=DragonAnalysisRuntime(sqlite3.connect(":memory:")); cp=rt.create("u","r",now=1,authorized=True)
    cp=rt.cancel("u","r",now=2,authorized=True)
    assert cp.cancelled and rt.next_dispatch("u","r",caps(),authorized=True) is None


def test_changed_receipt_replay_fails_closed():
    rt=DragonAnalysisRuntime(sqlite3.connect(":memory:")); cp=rt.create("u","r",now=1,authorized=True)
    d=rt.next_dispatch("u","r",caps(),authorized=True)
    cp=rt.commit_receipt("u","r",LayerReceipt(d.layer,(),"a"*64,1,True),now=2,
        expected_revision=cp.revision,authorized=True)
    with pytest.raises(ValueError,match="replay conflict"):
        rt.commit_receipt("u","r",LayerReceipt(d.layer,(),"b"*64,1,True),now=3,
            expected_revision=cp.revision,authorized=True)


def test_invalid_dependency_receipt_cannot_be_injected():
    rt=DragonAnalysisRuntime(sqlite3.connect(":memory:")); cp=rt.create("u","r",now=1,authorized=True)
    bad=LayerReceipt(AnalysisLayer.TEMPORAL_SEGMENTATION,("a"*64,),"b"*64,1,True)
    with pytest.raises(ValueError,match="violates"):
        rt.commit_receipt("u","r",bad,now=2,expected_revision=cp.revision,authorized=True)
