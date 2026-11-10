"""Quarantine ECS agent behavior: pure AST and finite spatial sensing."""
import math
import pytest
from skeleton.ecs.ai import agent_component, brain_component, validate_condition, check_condition, choose_utility, curve, steering, install_ai
from skeleton.simulation.ecs.errors import ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.ticker import TickScheduler


@pytest.mark.parametrize("invalid",[{"always":"true"},{"all":[]},{"any":[]},
    {"op":"lt","key":"x","value":float("nan")},
    {"op":"lt","key":"x","value":2,"exec":"injection"},
    {"op":"eq","key":"x","value":object()}])
def test_condition_contract_fail_closed(invalid):
    with pytest.raises(ValidationError):
        validate_condition(invalid)


def test_cycles_and_oversized_bool_tree_rejected():
    cond={"not":{}}
    cond["not"]=cond
    with pytest.raises(ValidationError):
        validate_condition(cond)
    with pytest.raises(ValidationError):
        validate_condition({"all":[{"always":True}]*1000})


def test_utility_nonfinite_and_invalid_weights_rejected():
    # Oversized Python integers must fail as ValidationError, not escape as
    # a conversion OverflowError from math.isfinite.
    for bad in (float("nan"),float("inf"),-1,10**1000):
        with pytest.raises(ValidationError):
            curve("linear",bad)
        with pytest.raises(ValidationError):
            choose_utility([{"action":"seek","need":"h","weight":bad}],{"h":0.5})


def test_agent_goals_and_brains_have_admission_budgets():
    with pytest.raises(ValidationError):
        agent_component(max_speed=float("nan"))
    with pytest.raises(ValidationError):
        agent_component(max_speed=10**1000)
    with pytest.raises(ValidationError):
        agent_component(goal=(10**1000, 0))
    with pytest.raises(ValidationError):
        agent_component(goal=(i for i in range(10000000)))
    with pytest.raises(ValidationError):
        brain_component("a",({"to":"b"} for _ in range(129)))


def test_steering_nan_cannot_poison_velocity():
    with pytest.raises(ValidationError):
        steering("seek",(0,float("nan")),(0,0),{"max_speed":4},(5,5))


@pytest.mark.parametrize(("field", "bad"), [
    ("max_speed", 10**1000),
    ("max_speed", True),
    ("pos", (10**1000, 0)),
    ("vel", (0, 10**1000)),
    ("target_pos", (0, 10**1000)),
    ("target_vel", (10**1000, 0)),
    ("wander_angle", 10**1000),
    ("pos", (0,)),
    ("vel", (0, 0, 0)),
])
def test_steering_rejects_oversized_or_malformed_inputs(field, bad):
    values = {
        "behavior": "seek", "pos": (0, 0), "vel": (0, 0),
        "agent": {"max_speed": 4}, "target_pos": (5, 5),
        "target_vel": (0, 0), "wander_angle": 0,
    }
    if field == "max_speed":
        values["agent"] = {"max_speed": bad}
    else:
        values[field] = bad
    with pytest.raises(ValidationError):
        steering(**values)


@pytest.mark.parametrize("radius", (10**1000, 0, -1, float("nan"), float("inf")))
def test_arrival_rejects_invalid_radius_before_float_conversion(radius):
    with pytest.raises(ValidationError):
        steering("arrive", (0, 0), (0, 0), {"max_speed": 4, "radius": radius}, (5, 5))


def test_sense_radius_is_bounded_before_registration():
    world=LiveWorld()
    tick=TickScheduler(fixed_dt=1/30)
    with pytest.raises(ValidationError):
        install_ai(tick,world,view_radius=float("inf"))
    with pytest.raises(ValidationError):
        install_ai(tick,world,view_radius=10**1000)


def test_oversized_perception_rejects_before_spatial_bucket_or_write():
    from unittest.mock import Mock
    from skeleton.ecs.ai import sense
    class OversizedContext:
        def __init__(self):
            self.set = Mock()
        def query(self, *components):
            if components == ("transform",):
                return iter([(1, {"x": 10**1000, "y": 0.0})])
            raise AssertionError("perception should reject coordinates before querying agents")
    ctx = OversizedContext()
    with pytest.raises(ValidationError, match="finite perception"):
        sense(ctx, 8.0)
    ctx.set.assert_not_called()


def test_dense_perception_budget_refuses_before_any_brain_write():
    from unittest.mock import Mock
    from skeleton.ecs.ai import sense, MAX_SENSE_CANDIDATES_PER_TICK
    # A hostile dense input would otherwise scan every agent against every
    # other agent. 1,100 agents in one cell already exceed the pair cap.
    count = 1100
    assert count * count > MAX_SENSE_CANDIDATES_PER_TICK
    class DenseContext:
        def __init__(self):
            self.set = Mock()
        def query(self, *components):
            if components == ("transform",):
                return iter((i, {"x": 0.0, "y": 0.0}) for i in range(count))
            if components == ("agent", "brain"):
                return iter((i, {"target": None}, {"memory": {}}) for i in range(count))
            raise AssertionError("unexpected query")
    ctx = DenseContext()
    with pytest.raises(ValidationError, match="pair budget"):
        sense(ctx, 8.0)
    ctx.set.assert_not_called()


def test_hostile_perception_coordinates_are_rejected_without_float_hooks():
    from unittest.mock import Mock
    from skeleton.ecs.ai import sense
    class Hostile(float):
        def __float__(self):
            raise AssertionError("untrusted float hook called")
    class Context:
        def __init__(self):
            self.set=Mock()
        def query(self, *components):
            if components == ("transform",):
                return iter([(1, {"x": Hostile(0.0), "y": 0.0})])
            if components == ("agent", "brain"):
                return iter([(1, {"target": None}, {"memory": {}})])
            raise AssertionError("unexpected query")
    ctx=Context()
    with pytest.raises(ValidationError,match="finite perception"):
        sense(ctx, 8.0)
    ctx.set.assert_not_called()
