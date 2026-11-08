"""Review-only privacy and secret-exposure signals inside selected web evidence.

The scanner never returns matched values, offsets or source page bodies. It
does not establish whether a value is personal, sensitive, genuine or a secret.
Policy and privacy officers must decide handling at the current source owner.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import re

from ..contracts import digest
from .frames import FrameSet


_RULES = (
    ("email_address", re.compile(r"(?<![\w.-])[\w.+-]{1,64}@[\w.-]{1,128}\.[A-Za-z]{2,24}\b")),
    ("possible_bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{18,}", re.I)),
    ("possible_private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("possible_api_credential", re.compile(r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", re.I)),
    ("cloud_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("possible_password_assignment", re.compile(r"\b(?:password|passwd)\s*[:=]\s*[^\s'\"]{8,}", re.I)),
)


@dataclass(frozen=True)
class PrivacySignal:
    source_id: str
    passage_hash: str
    rule_codes: tuple[str, ...]
    suspected_value_count: int
    policy_review_required: bool = True
    personal_data_verified: bool = False
    credential_validity_tested: bool = False


@dataclass(frozen=True)
class PrivacySignalReport:
    frame_set_digest: str
    findings: tuple[PrivacySignal, ...]
    held_source_ids: tuple[str, ...]
    redaction_review_needed: bool
    report_digest: str
    captured_values_exported: bool = False
    credential_network_test_performed: bool = False
    source_use_approval_granted: bool = False


def inspect_privacy_signals(frames: FrameSet) -> PrivacySignalReport:
    if not isinstance(frames, FrameSet):
        raise TypeError("exact source-bound frame set required")
    rows = []
    holds = set()
    for frame in frames.frames:
        codes = []
        hits = 0
        for code, pattern in _RULES:
            count = len(pattern.findall(frame.text))
            if count:
                codes.append(code)
                hits += count
        if codes:
            holds.add(frame.anchor.source_id)
        rows.append(PrivacySignal(
            frame.anchor.source_id, frame.anchor.passage_hash,
            tuple(sorted(codes)), hits,
        ))
    payload = {
        "frames": frames.frame_set_digest,
        "findings": [asdict(x) for x in rows],
    }
    return PrivacySignalReport(
        frames.frame_set_digest, tuple(rows), tuple(sorted(holds)),
        bool(holds), digest(payload),
    )
