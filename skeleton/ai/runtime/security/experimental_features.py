from dataclasses import dataclass


@dataclass(frozen=True)
class ExperimentKillSwitch:
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("kill switch state must be boolean")


@dataclass(frozen=True)
class ExperimentalFeature:
    feature_id: str
    scope: str
    production_capability: bool = False

    def __post_init__(self) -> None:
        if (
            not self.feature_id
            or not self.scope
            or not isinstance(self.production_capability, bool)
        ):
            raise ValueError("valid experimental feature required")


@dataclass(frozen=True)
class ExperimentExposure:
    feature: ExperimentalFeature
    traffic: str
    kill_switch: ExperimentKillSwitch
    active: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.feature, ExperimentalFeature)
            or self.traffic not in {"synthetic", "shadow"}
            or not isinstance(self.kill_switch, ExperimentKillSwitch)
            or not isinstance(self.active, bool)
        ):
            raise ValueError("valid experiment exposure required")
        if self.feature.production_capability and self.active:
            raise ValueError("production capability cannot be active experimentally")
        if self.kill_switch.enabled and self.active:
            raise ValueError("enabled kill switch cannot have active exposure")


def expose(
    feature: ExperimentalFeature,
    traffic: str,
    kill_switch: ExperimentKillSwitch,
) -> ExperimentExposure:
    if not isinstance(feature, ExperimentalFeature) or not isinstance(
        kill_switch, ExperimentKillSwitch
    ):
        raise ValueError("valid experiment identity and controls required")
    if feature.production_capability:
        raise PermissionError("experiment cannot satisfy production capability")
    if traffic not in {"synthetic", "shadow"}:
        raise PermissionError("experimental traffic must be isolated")
    return ExperimentExposure(
        feature,
        traffic,
        kill_switch,
        not kill_switch.enabled,
    )


def apply_kill_switch(
    exposure: ExperimentExposure,
    kill_switch: ExperimentKillSwitch,
) -> ExperimentExposure:
    if not isinstance(exposure, ExperimentExposure) or not isinstance(
        kill_switch, ExperimentKillSwitch
    ):
        raise ValueError("experiment exposure and kill switch required")
    # A stopped exposure is monotonic. A later false switch may authorize a
    # fresh exposure through expose(), but cannot resurrect an old receipt.
    active = exposure.active and not kill_switch.enabled
    return ExperimentExposure(
        exposure.feature,
        exposure.traffic,
        kill_switch,
        active,
    )
