from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderParity:
    capability: bool
    policy: bool
    quality: bool
    cost: bool
    data_boundary: bool

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (
                self.capability,
                self.policy,
                self.quality,
                self.cost,
                self.data_boundary,
            )
        ):
            raise ValueError("provider parity assertions must be boolean")

    @property
    def complete(self) -> bool:
        return all(
            (
                self.capability,
                self.policy,
                self.quality,
                self.cost,
                self.data_boundary,
            )
        )


@dataclass(frozen=True)
class ProviderMigration:
    source: str
    target: str
    parity: ProviderParity
    stage: str = "shadow"

    def __post_init__(self) -> None:
        if (
            not self.source
            or not self.target
            or self.source == self.target
            or not isinstance(self.parity, ProviderParity)
            or self.stage not in {"shadow", "canary"}
        ):
            raise ValueError("valid provider migration required")


@dataclass(frozen=True)
class ProviderCutover:
    source: str
    target: str
    active: str
    rollback: str


def promote_to_canary(migration: ProviderMigration) -> ProviderMigration:
    if not isinstance(migration, ProviderMigration):
        raise ValueError("provider migration required")
    if migration.stage != "shadow":
        raise ValueError("only shadow migration can promote to canary")
    if not migration.parity.complete:
        raise PermissionError("provider parity incomplete")
    return ProviderMigration(
        migration.source,
        migration.target,
        migration.parity,
        "canary",
    )


def cutover(migration: ProviderMigration) -> ProviderCutover:
    if not isinstance(migration, ProviderMigration):
        raise ValueError("provider migration required")
    if not migration.parity.complete:
        raise PermissionError("provider parity incomplete")
    if migration.stage != "canary":
        raise PermissionError("provider must pass canary before cutover")
    return ProviderCutover(
        migration.source,
        migration.target,
        migration.target,
        migration.source,
    )


def rollback(cutover_receipt: ProviderCutover) -> ProviderCutover:
    if not isinstance(cutover_receipt, ProviderCutover):
        raise ValueError("provider cutover receipt required")
    return ProviderCutover(
        cutover_receipt.target,
        cutover_receipt.source,
        cutover_receipt.rollback,
        cutover_receipt.active,
    )
