from dataclasses import dataclass
import math


@dataclass(frozen=True)
class DataLocation:
    region: str
    freshness: int
    classification: str

    def __post_init__(self) -> None:
        if not self.region or not self.classification:
            raise ValueError("complete data location required")
        if (
            isinstance(self.freshness, bool)
            or not isinstance(self.freshness, int)
            or self.freshness < 0
        ):
            raise ValueError("nonnegative freshness required")


@dataclass(frozen=True)
class LocalityConstraint:
    allowed_regions: frozenset[str]
    max_age: int
    allowed_classifications: frozenset[str] = frozenset({"public"})

    def __post_init__(self) -> None:
        if (
            not isinstance(self.allowed_regions, frozenset)
            or not self.allowed_regions
            or any(not region for region in self.allowed_regions)
        ):
            raise ValueError("allowed regions required")
        if (
            not isinstance(self.allowed_classifications, frozenset)
            or not self.allowed_classifications
            or any(not value for value in self.allowed_classifications)
        ):
            raise ValueError("allowed classifications required")
        if (
            isinstance(self.max_age, bool)
            or not isinstance(self.max_age, int)
            or self.max_age < 0
        ):
            raise ValueError("nonnegative max_age required")


@dataclass(frozen=True)
class TransferPlan:
    source: DataLocation
    target_region: str
    cost: float
    allowed: bool


def plan_transfer(
    source: DataLocation,
    target: str,
    constraint: LocalityConstraint,
    cost: float,
) -> TransferPlan:
    if not isinstance(source, DataLocation) or not isinstance(
        constraint, LocalityConstraint
    ):
        raise ValueError("data location and locality constraint required")
    if not target:
        return TransferPlan(source, target, cost, False)
    if (
        source.region not in constraint.allowed_regions
        or target not in constraint.allowed_regions
        or source.classification not in constraint.allowed_classifications
    ):
        return TransferPlan(source, target, cost, False)
    if source.freshness > constraint.max_age:
        return TransferPlan(source, target, cost, False)
    if (
        isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
    ):
        return TransferPlan(source, target, cost, False)
    return TransferPlan(source, target, float(cost), True)
