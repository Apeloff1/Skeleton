from dataclasses import dataclass


@dataclass(frozen=True)
class UsageGrant:
    purpose: str
    geography: frozenset[str]
    retain_until: int
    training: bool

    def __post_init__(self) -> None:
        if not self.purpose or not isinstance(self.geography, frozenset) or not self.geography:
            raise ValueError("grant purpose and geography required")
        if any(not region for region in self.geography):
            raise ValueError("invalid grant geography")
        if (
            isinstance(self.retain_until, bool)
            or not isinstance(self.retain_until, int)
            or self.retain_until < 0
            or not isinstance(self.training, bool)
        ):
            raise ValueError("invalid grant retention/training policy")


@dataclass(frozen=True)
class DataRights:
    data_id: str
    grants: tuple[UsageGrant, ...]
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.data_id:
            raise ValueError("data rights identity required")
        if any(not isinstance(grant, UsageGrant) for grant in self.grants):
            raise ValueError("usage grants required")
        if any(not item for item in self.lineage):
            raise ValueError("invalid rights lineage")
        if self.data_id in self.lineage or len(self.lineage) != len(set(self.lineage)):
            raise ValueError("cyclic or duplicate rights lineage")


@dataclass(frozen=True)
class RightsDecision:
    allowed: bool
    reason: str


def decide(
    rights: DataRights,
    purpose: str,
    geo: str,
    now: int,
    training: bool = False,
) -> RightsDecision:
    if (
        not isinstance(rights, DataRights)
        or not purpose
        or not geo
        or isinstance(now, bool)
        or not isinstance(now, int)
        or now < 0
        or not isinstance(training, bool)
    ):
        return RightsDecision(False, "invalid rights query")

    matched = any(
        grant.purpose == purpose
        and geo in grant.geography
        and now <= grant.retain_until
        and (not training or grant.training)
        for grant in rights.grants
    )
    return RightsDecision(
        matched,
        "grant matched" if matched else "no compatible grant",
    )


def derive(parent: DataRights, new_id: str) -> DataRights:
    if not isinstance(parent, DataRights):
        raise ValueError("parent rights required")
    if (
        not new_id
        or new_id == parent.data_id
        or new_id in parent.lineage
    ):
        raise ValueError("derived data requires new lineage identity")
    lineage = parent.lineage + (parent.data_id,)
    return DataRights(new_id, parent.grants, lineage)
