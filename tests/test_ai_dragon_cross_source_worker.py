"""Cross-source corroboration regressions."""
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_cross_source_worker import execute_cross_source_corroboration
from skeleton.ai.webcrawler.dragon_causal_falsification_worker import FalsificationOutcome
from skeleton.ai.webcrawler.dragon_mechanic_causal_analysis import MechanicEffect
from skeleton.ai.webcrawler.dragon_source_independence import SourceProvenance


def effect():
    return MechanicEffect("m",10,10,.8,.2,.6,(.1,.9),True,True,"p",2,())


def outcome(h="h",v="supported"):
    return FalsificationOutcome(h,v,effect(),"e"*64)


def base():
    r=LayerReceipt(AnalysisLayer.CAUSAL_FALSIFICATION,("a"*64,),"b"*64,2,True,False)
    d=LayerDispatch(AnalysisLayer.CROSS_SOURCE_CORROBORATION,("b"*64,),"cross","v1")
    return r,d


def src(s,digest,uri,parents=()):
    return SourceProvenance(s,digest,uri,parents,())


def test_two_independent_sources_corroborate():
    r,d=base(); p=(src("s1","1"*64,"https://a/x"),src("s2","2"*64,"https://b/y"))
    out=execute_cross_source_corroboration(d,(("s1",outcome()),("s2",outcome())),
        falsification_receipt=r,provenance=p,authorized=True)
    assert out.claims[0].corroborated
    assert out.receipt.independent_sources==2


def test_copied_sources_count_once():
    r,d=base(); p=(src("s1","1"*64,"https://a/x"),src("s2","1"*64,"https://b/y"))
    out=execute_cross_source_corroboration(d,(("s1",outcome()),("s2",outcome())),
        falsification_receipt=r,provenance=p,authorized=True)
    assert not out.claims[0].corroborated
    assert out.receipt.independent_sources==0


def test_derived_sources_count_once():
    r,d=base(); p=(src("s1","1"*64,"https://a/x"),src("s2","2"*64,"https://b/y",("s1",)))
    out=execute_cross_source_corroboration(d,(("s1",outcome()),("s2",outcome())),
        falsification_receipt=r,provenance=p,authorized=True)
    assert not out.claims[0].corroborated


def test_opposing_independent_cluster_prevents_promotion():
    r,d=base(); p=(src("s1","1"*64,"https://a/x"),src("s2","2"*64,"https://b/y"),
        src("s3","3"*64,"https://c/z"))
    out=execute_cross_source_corroboration(d,(("s1",outcome()),("s2",outcome()),
        ("s3",outcome(v="refuted"))),falsification_receipt=r,provenance=p,authorized=True)
    assert out.claims[0].verdict=="inconclusive"


def test_unknown_source_fails_closed():
    r,d=base(); p=(src("s1","1"*64,"https://a/x"),)
    try:
        execute_cross_source_corroboration(d,(("missing",outcome()),),
            falsification_receipt=r,provenance=p,authorized=True)
        assert False
    except ValueError as exc: assert "provenance" in str(exc)
