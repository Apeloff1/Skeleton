"""Bounced first-install qualification parameters and explicit safety holds."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ...orchestration.execution_spine.contracts import identifier, SpineError

class QualificationError(RuntimeError):
    """Production qualification cannot be safely proven."""


@dataclass(frozen=True, slots=True)
class QualificationInput:
    model_root: Path
    state_dir: Path
    tenant: str
    subject: str
    n_ctx: int = 2048
    max_new_tokens: int = 64
    n_threads: int = 2
    gpu_layers: int = 0
    seed: int = 117
    prompt: str = 'Explain briefly why an offline model should preserve durable chat state.'

    def __post_init__(self):
        identifier(self.tenant, 'qualification tenant')
        identifier(self.subject, 'qualification subject')
        if type(self.n_ctx) is not int or not 128 <= self.n_ctx <= 131072:
            raise QualificationError('invalid native qualification context')
        if type(self.max_new_tokens) is not int or not 1 <= self.max_new_tokens < self.n_ctx:
            raise QualificationError('invalid qualification generation bound')
        if type(self.n_threads) is not int or not 1 <= self.n_threads <= 64:
            raise QualificationError('invalid qualification thread bound')
        if type(self.gpu_layers) is not int or not 0 <= self.gpu_layers <= 1024:
            raise QualificationError('invalid GPU placement bound')
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise QualificationError('invalid deterministic qualification seed')
        if not isinstance(self.prompt,str) or not self.prompt.strip() or len(self.prompt.encode('utf8')) > 1024:
            raise QualificationError('qualification prompt must be explicit and bounded')
