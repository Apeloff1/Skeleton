from dataclasses import dataclass


@dataclass(frozen=True)
class DrainState:
    in_flight: int
    pinned: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.in_flight, bool)
            or not isinstance(self.in_flight, int)
            or self.in_flight < 0
            or not isinstance(self.pinned, bool)
        ):
            raise ValueError("invalid drain state")

    @property
    def safe(self) -> bool:
        return not self.pinned and self.in_flight == 0


@dataclass(frozen=True)
class EvictionPolicy:
    min_idle: int
    allow_reload: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_idle, bool)
            or not isinstance(self.min_idle, int)
            or self.min_idle < 0
            or not isinstance(self.allow_reload, bool)
        ):
            raise ValueError("invalid eviction policy")


@dataclass(frozen=True)
class ModelEviction:
    model_id: str
    reason: str
    reloadable: bool

    def __post_init__(self) -> None:
        if not self.model_id or not self.reason or not isinstance(self.reloadable, bool):
            raise ValueError("invalid model eviction")


def evict(
    model_id: str,
    state: DrainState,
    policy: EvictionPolicy,
    idle: int,
    *,
    reason: str = "idle-pressure",
) -> ModelEviction:
    if not model_id or not isinstance(state, DrainState) or not isinstance(policy, EvictionPolicy):
        raise ValueError("valid model, drain state, and eviction policy required")
    if isinstance(idle, bool) or not isinstance(idle, int) or idle < 0:
        raise ValueError("valid model and idle duration required")
    if not reason:
        raise ValueError("eviction reason required")
    if not state.safe:
        raise PermissionError("model not at safe eviction boundary")
    if idle < policy.min_idle:
        raise PermissionError("eviction would thrash")
    return ModelEviction(model_id, reason, policy.allow_reload)
