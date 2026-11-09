"""Public, bounded contracts for independently provisioned local model workers."""
from __future__ import annotations
from dataclasses import dataclass
import re

_DIGEST = re.compile(r'^[0-9a-f]{64}$')


class AdmissionError(RuntimeError):
    """Model resource admission is uncertain or violates an explicit bound."""


class AdmissionBusy(AdmissionError):
    """Other admitted workers already occupy the configured budget."""


class AdmissionCorrupt(AdmissionError):
    """The model-capacity registry cannot be independently verified."""


class AdmissionUnsupported(AdmissionError):
    """Required process, operating-system or filesystem custody is absent."""


def integer(raw: object, name: str, minimum: int, maximum: int) -> int:
    if type(raw) is not int or not minimum <= raw <= maximum:
        raise AdmissionError(f'invalid {name} bound')
    return raw


def sha256(raw: object, name: str) -> str:
    if not isinstance(raw, str) or _DIGEST.fullmatch(raw) is None:
        raise AdmissionError(f'invalid {name} identity')
    return raw


@dataclass(frozen=True, slots=True)
class CapacityPolicy:
    slots: int = 1
    budget_bytes: int = 8_000_000_000
    minimum_host_margin_bytes: int = 512_000_000

    def __post_init__(self) -> None:
        integer(self.slots, 'model slots', 1, 32)
        integer(self.budget_bytes, 'model capacity budget', 268_435_456, 64_000_000_000)
        integer(self.minimum_host_margin_bytes, 'host safety margin', 268_435_456, 8_000_000_000)

    def record(self) -> dict:
        return {'version': 1, 'slots': self.slots, 'budget_bytes': self.budget_bytes,
                'minimum_host_margin_bytes': self.minimum_host_margin_bytes}

    @classmethod
    def parse(cls, raw: dict) -> 'CapacityPolicy':
        if type(raw) is not dict or set(raw) != {'version','slots','budget_bytes','minimum_host_margin_bytes'}:
            raise AdmissionCorrupt('model capacity policy schema differs')
        if type(raw['version']) is not int or raw['version'] != 1:
            raise AdmissionCorrupt('unsupported model capacity policy version')
        try:
            return cls(raw['slots'], raw['budget_bytes'], raw['minimum_host_margin_bytes'])
        except AdmissionError as exc:
            raise AdmissionCorrupt('invalid persisted model policy') from exc


@dataclass(frozen=True, slots=True)
class Reservation:
    model_sha256: str
    principal_sha256: str
    manifest_sha256: str
    reserve_bytes: int

    def __post_init__(self):
        for value, name in [(self.model_sha256, 'model'),
                            (self.principal_sha256, 'principal'),
                            (self.manifest_sha256, 'manifest')]:
            sha256(value, name)
        integer(self.reserve_bytes, 'requested model reservation', 1, 64_000_000_000)

    def record(self) -> dict:
        return {'model_sha256': self.model_sha256,
                'principal_sha256': self.principal_sha256,
                'manifest_sha256': self.manifest_sha256,
                'reserve_bytes': self.reserve_bytes}
