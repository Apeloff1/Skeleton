"""Regressions for executable falsifiable mechanic-hypothesis generation."""
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_hypothesis_worker import execute_hypothesis_generation
from skeleton.ai.webcrawler.dragon_state_inference_worker import TrackState


def inputs():
    receipt=LayerReceipt(AnalysisLayer.STATE_INFERENCE,("a"*64,),"b"*64,2,True,False)
    dispatch=LayerDispatch(AnalysisLayer.MECHANIC_HYPOTHESES,("b"*64,),"hypothesis","v1")
    moving=TrackState("t1","avatar",0,100,3,.2,.9,"moving")
    still=TrackState("t2","wall",0,100,3,0,.99,"stationary_or_unresolved")
    return receipt,dispatch,(moving,still)


def test_only_observed_motion_generates_candidate():
    r,d,states=inputs(); out=execute_hypothesis_generation(
        d,states,state_receipt=r,authorized=True)
    assert len(out.candidates)==1
    c=out.candidates[0]
    assert "may alter" in c.hypothesis.statement
    assert c.alternative_explanation
    assert c.hypothesis.source_fingerprint==r.output_fingerprint


def test_candidate_is_explicitly_falsifiable_and_measurable():
    r,d,states=inputs(); c=execute_hypothesis_generation(
        d,states,state_receipt=r,authorized=True).candidates[0]
    assert "no reproducible" in c.hypothesis.falsifying_observation
    assert "displacement" in c.measured_outcome
    assert "pre-registered" in c.intervention


def test_dependency_substitution_fails_closed():
    r,d,states=inputs()
    bad=LayerDispatch(AnalysisLayer.MECHANIC_HYPOTHESES,("c"*64,),"hypothesis","v1")
    try:
        execute_hypothesis_generation(bad,states,state_receipt=r,authorized=True)
        assert False
    except ValueError as exc:
        assert "mismatch" in str(exc)


def test_output_is_deterministic():
    r,d,states=inputs()
    a=execute_hypothesis_generation(d,states,state_receipt=r,authorized=True)
    b=execute_hypothesis_generation(d,tuple(reversed(states)),state_receipt=r,authorized=True)
    assert a.receipt.output_fingerprint==b.receipt.output_fingerprint
