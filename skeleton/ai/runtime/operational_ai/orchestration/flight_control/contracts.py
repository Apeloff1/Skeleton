"""Durable inference admission contract. No task may invent a model response."""
from __future__ import annotations
from dataclasses import dataclass
from ..execution_spine.contracts import Identity, InferenceRequest, SpineError, identifier, digest


class FlightError(SpineError):
    """An inference queue invariant failed closed."""


class FlightConflict(FlightError):
    """A durable ticket conflicts with observed ownership or input."""


class FlightBusy(FlightError):
    """Queue capacity or an active lease prevents admission."""


@dataclass(frozen=True, slots=True)
class FlightSpec:
    """Signed-by-identity (digest, not cryptographic signature) inference intent."""
    identity: Identity
    job_id: str
    session: str
    request_id: str
    prompt: str
    seed: int = 0
    temperature: float = 0.8
    priority: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.identity, Identity):
            raise FlightError('identity required')
        identifier(self.job_id, 'job')
        req = self.request()
        if type(self.priority) is not int or not 0 <= self.priority <= 9:
            raise FlightError('priority must be an integer in [0,9]')
        if len(req.prompt.encode('utf8')) > 32768:
            raise FlightError('queued plaintext exceeds 32 KiB')

    def request(self) -> InferenceRequest:
        return InferenceRequest(self.identity, self.session, self.request_id,
                                self.prompt, self.seed, self.temperature)

    def fingerprint(self) -> str:
        return digest({'schema':'skeleton.flight.v1', 'job_id':self.job_id,
                       'request':self.request().bound_digest(), 'session':self.session,
                       'request_id':self.request_id, 'priority':self.priority})


@dataclass(frozen=True, slots=True)
class FlightPolicy:
    max_queued: int = 512
    max_per_principal: int = 128
    max_running: int = 8
    max_claimed: int = 16
    lease_ms: int = 15_000
    max_probe: int = 1024

    def __post_init__(self):
        for key, max_value in (('max_queued',4096),('max_per_principal',4096),
                               ('max_running',128),('max_claimed',128),
                               ('lease_ms',600000),('max_probe',4096)):
            value=getattr(self,key)
            if type(value) is not int or not 1<=value<=max_value:
                raise FlightError(f'invalid {key}')
        if self.max_per_principal>self.max_queued:
            raise FlightError('per-principal queue limit cannot exceed global limit')
        if self.max_running>self.max_claimed:
            raise FlightError('running ceiling cannot exceed claimed ceiling')


@dataclass(frozen=True, slots=True)
class Ticket:
    job_id: str
    worker: str
    fence: int
    boot: str
    expires_ns: int

    def __post_init__(self) -> None:
        identifier(self.job_id,'job');identifier(self.worker,'worker')
        if type(self.fence)is not int or self.fence<1:raise FlightError('invalid claim fence')
        if not isinstance(self.boot,str) or len(self.boot)!=36:raise FlightError('invalid boot fence')
        if type(self.expires_ns)is not int or self.expires_ns<1:raise FlightError('invalid claim deadline')


STATES=frozenset(('queued','claimed','running','completed','held','cancelled'))
TERMINAL=frozenset(('completed','held','cancelled'))
