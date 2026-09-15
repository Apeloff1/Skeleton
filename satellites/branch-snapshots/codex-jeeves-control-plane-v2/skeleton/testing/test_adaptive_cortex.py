from skeleton.cortex.adaptive import AdaptiveController, EarlyExit, InferenceBudget
from skeleton.cortex.batch import BatchRequest, BatchScheduler
from skeleton.cortex.speculative import SpeculativeDecoder
from skeleton.cortex.uncertainty import confidence, entropy, margin, normalized_entropy


def test_adaptive_plan_scales_with_risk():
    controller = AdaptiveController(InferenceBudget(max_layers=8, max_tokens=16, max_verifiers=2, min_confidence=0.8))
    low = controller.plan(confidence=0.99)
    high = controller.plan(uncertainty=1.0, novelty=1.0, risk=1.0, confidence=0.2)
    assert high.layers >= low.layers
    assert high.verifiers >= 1
    assert high.confidence_target >= 0.8


def test_early_exit_has_minimum_depth():
    gate = EarlyExit(0.9, min_layers=3)
    assert not gate.should_stop(layer=2, confidence=1.0)
    assert gate.should_stop(layer=3, confidence=0.95)
    assert not gate.should_stop(layer=3, confidence=0.95, stable=False)


def test_uncertainty_estimators_are_bounded():
    assert entropy([0.5, 0.5]) > 0
    assert normalized_entropy([0.5, 0.5]) == 1.0
    assert 0.0 <= margin([0.9, 0.1]) <= 1.0
    assert 0.0 <= confidence([0.9, 0.1]) <= 1.0


def test_batch_scheduler_is_stable_and_bounded():
    scheduler = BatchScheduler(max_batch=2, max_cost=3)
    assert scheduler.submit(BatchRequest("b", 2, priority=1, cost=2))
    assert scheduler.submit(BatchRequest("a", 1, priority=2, cost=1))
    assert not scheduler.submit(BatchRequest("a", 9))
    batch = scheduler.drain()
    assert batch is not None
    assert [r.request_id for r in batch.requests] == ["a", "b"]
    assert batch.total_cost == 3


def test_speculative_decoder_stops_at_first_rejection():
    decoder = SpeculativeDecoder(max_proposals=4)
    result = decoder.decode(
        lambda prefix, n: [1, 2, 3, 4],
        lambda prefix, token: token < 3,
        [0],
    )
    assert result.accepted == (1, 2)
    assert result.rejected == (3, 4)
    assert result.acceptance_rate == 0.5
