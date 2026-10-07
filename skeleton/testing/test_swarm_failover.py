from skeleton.agents.swarm_failover import FailoverCoordinator, ReplicaState


def test_failover_prefers_highest_epoch_then_sequence() -> None:
    coordinator = FailoverCoordinator()
    replicas = {
        "a": ReplicaState("a", epoch=1, sequence=100),
        "b": ReplicaState("b", epoch=2, sequence=10),
        "c": ReplicaState("c", epoch=2, sequence=11),
    }
    decision = coordinator.elect(replicas)
    assert decision.leader_id == "c"
    assert decision.epoch == 2


def test_failover_ignores_unhealthy_replica() -> None:
    coordinator = FailoverCoordinator()
    replicas = {
        "a": ReplicaState("a", epoch=3, sequence=100, healthy=False),
        "b": ReplicaState("b", epoch=2, sequence=10),
    }
    assert coordinator.elect(replicas).leader_id == "b"


def test_failover_returns_none_without_healthy_replicas() -> None:
    decision = FailoverCoordinator().elect({"a": ReplicaState("a", 1, 1, False)})
    assert decision.leader_id is None


def test_promotion_requires_non_regressing_epoch() -> None:
    coordinator = FailoverCoordinator()
    assert coordinator.can_promote(ReplicaState("a", 4, 1), current_epoch=4)
    assert not coordinator.can_promote(ReplicaState("a", 3, 100), current_epoch=4)
