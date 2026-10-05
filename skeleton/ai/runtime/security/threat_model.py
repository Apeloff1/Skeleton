"""Executable unified threat-model coverage contracts for VOL-026."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from skeleton.contracts.canonical import canonical_json_bytes

from .contracts import SecurityContractError


_REQUIRED = frozenset(
    {
        "tool-authority",
        "secrets",
        "filesystem",
        "network-egress",
        "supply-chain",
    }
)


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SecurityContractError(f"invalid {field}")
    if len(value) > maximum:
        raise SecurityContractError(f"invalid {field}")
    return value


@dataclass(frozen=True, slots=True)
class Threat:
    threat_id: str
    asset: str
    boundary: str
    mitigation: str
    validation: str

    def __post_init__(self) -> None:
        for field in (
            "threat_id",
            "asset",
            "boundary",
            "mitigation",
            "validation",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field),
            )


@dataclass(frozen=True, slots=True)
class ThreatModel:
    threats: tuple[Threat, ...]
    model_version: str = "vol026-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.threats, tuple) or not self.threats:
            raise SecurityContractError("threats required")
        if any(not isinstance(item, Threat) for item in self.threats):
            raise SecurityContractError("threats must contain Threat values")
        object.__setattr__(
            self,
            "model_version",
            _text(self.model_version, "model_version", maximum=128),
        )
        ids = [item.threat_id for item in self.threats]
        if len(ids) != len(set(ids)):
            raise SecurityContractError("duplicate threat id")
        assets = {item.asset for item in self.threats}
        missing = _REQUIRED - assets
        if missing:
            raise SecurityContractError(
                "missing required threat coverage: "
                + ",".join(sorted(missing))
            )
        object.__setattr__(
            self,
            "threats",
            tuple(sorted(self.threats, key=lambda item: item.threat_id)),
        )

    @property
    def digest(self) -> str:
        return sha256(
            canonical_json_bytes(
                {
                    "version": self.model_version,
                    "threats": [
                        {
                            "id": item.threat_id,
                            "asset": item.asset,
                            "boundary": item.boundary,
                            "mitigation": item.mitigation,
                            "validation": item.validation,
                        }
                        for item in self.threats
                    ],
                }
            )
        ).hexdigest()


def canonical_vol026_threat_model() -> ThreatModel:
    return ThreatModel(
        (
            Threat(
                "T-AUTH-001",
                "tool-authority",
                "planner-to-tool",
                "exact capability/resource/operation grant",
                "skeleton/testing/test_vol026_capability_security.py",
            ),
            Threat(
                "T-SECRET-001",
                "secrets",
                "secret-store-to-runtime",
                "reference-only SecretRef",
                "skeleton/testing/test_vol026_capability_security.py",
            ),
            Threat(
                "T-FS-001",
                "filesystem",
                "input-to-rooted-filesystem",
                "rooted path and archive sandbox enforcement",
                "skeleton/testing/test_security_rooted_fs.py",
            ),
            Threat(
                "T-NET-001",
                "network-egress",
                "runtime-to-network",
                "resolved destination plus connected-peer validation",
                "skeleton/testing/test_security_outbound_http.py",
            ),
            Threat(
                "T-SUPPLY-001",
                "supply-chain",
                "dependency-to-runtime",
                "repository SAST and dependency integrity controls",
                "scripts/check_repository_python_sast.py",
            ),
        )
    )


__all__ = [
    "Threat",
    "ThreatModel",
    "canonical_vol026_threat_model",
]
