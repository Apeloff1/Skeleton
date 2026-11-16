"""Independently administered, exact-content reviewer policy.

This deliberately does not import the application, invoke a model, or accept
instructions as policy. An operator independently approves exact context
digests and challenge scopes. Unknown contexts are signed DENY, not implicitly
allowed. This release candidate is a strict review queue endpoint, not a
semantic adversarial classifier or proof of physical administrative separation.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from threading import Lock
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REVIEW_SCHEMA = "skeleton.guard.review-request.v1"
VERDICT_SCHEMA = "skeleton.guard.signed-review.v1"
ATTEST_SCHEMA = "skeleton.guard.reviewer-custody.v1"
VERDICT_DOMAIN = b"skeleton.guard.signed-review.v1\x00"
POLICY_SCHEMA = "skeleton.guard.independent-exact-policy.v1"
MAX_TEXT = 1_048_576
MAX_REVIEW_BODY = 6 * MAX_TEXT + 4096
MAX_ATTEST_BODY = 4096
MAX_POLICY = 8 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_NONCE = re.compile(r"[0-9a-f]{48}\Z", re.ASCII)
_MAX_POLICY_LIFETIME = 86400
_MAX_APPROVALS = 50_000
_MAX_SCOPES = 2048
_MAX_REPLAY = 16384


class PolicyDenied(ValueError):
    """Redacted policy, request or custody rejection."""


def _require(condition):
    if condition is not True:
        raise PolicyDenied("independent reviewer denied request")


def _hex(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _identity(value):
    return (type(value) is str and 1 <= len(value) <= 128
            and all(33 <= ord(ch) <= 126 for ch in value))


def _scope(value):
    if (type(value) is not str or not 1 <= len(value) <= 512
            or value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        return False
    try:
        return len(value.encode("utf-8", "strict")) <= 512
    except UnicodeError:
        return False


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _unique(pairs):
    output = {}
    for k, v in pairs:
        _require(k not in output)
        output[k] = v
    return output


def _deny_constant(_):
    raise PolicyDenied("independent reviewer denied request")


def decode_document(raw, max_bytes):
    _require(type(raw) is bytes and 1 <= len(raw) <= max_bytes)
    try:
        obj = json.loads(raw.decode("utf-8", "strict"),
                         object_pairs_hook=_unique, parse_constant=_deny_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise PolicyDenied("independent reviewer denied request") from None
    _require(type(obj) is dict)
    return obj


def _read_regular(path, bound, *, secret=False):
    """Read an exact bounded file, never a symlink or a growing stream."""
    path = Path(path)
    _require(path.is_absolute())
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        def stamp(v):
            return v.st_dev, v.st_ino, v.st_mode, v.st_size, v.st_mtime_ns, v.st_ctime_ns
        _require(stat.S_ISREG(before.st_mode) and 1 <= before.st_size <= bound)
        _require(stamp(before) == stamp(path.lstat()))
        if secret:
            _require(before.st_uid == os.geteuid() and before.st_mode & 0o077 == 0)
        output = bytearray()
        while len(output) < before.st_size:
            chunk = os.read(fd, min(65536, before.st_size - len(output)))
            _require(bool(chunk))
            output.extend(chunk)
        _require(not os.read(fd, 1))
        _require(stamp(before) == stamp(os.fstat(fd)) == stamp(path.lstat()))
        return bytes(output)
    finally:
        os.close(fd)


def load_signer(path):
    key_bytes = _read_regular(path, 32, secret=True)
    _require(len(key_bytes) == 32)
    return Ed25519PrivateKey.from_private_bytes(key_bytes)


@dataclass(frozen=True, slots=True)
class ChallengeScope:
    tenant_id: str
    actor_id: str
    context_id: str
    model_digest: str
    runtime_digest: str
    tokenizer_digest: str

    def __post_init__(self):
        _require(all(_scope(v) for v in (self.tenant_id, self.actor_id, self.context_id)))
        _require(all(_hex(v) for v in (self.model_digest, self.runtime_digest, self.tokenizer_digest)))


@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    authority_id: str
    deployment_domain: str
    issued_at: int
    expires_at: int
    client_certificates: frozenset[str]
    approved_contexts: frozenset[str]
    challenge_scopes: frozenset[ChallengeScope]
    sha256: str

    def active(self, now):
        return type(now) is int and self.issued_at <= now < self.expires_at

    @classmethod
    def load(cls, path, expected_sha256):
        return cls.parse(_read_regular(path, MAX_POLICY), expected_sha256)

    @classmethod
    def parse(cls, raw, expected_sha256):
        _require(_hex(expected_sha256))
        _require(type(raw) is bytes and len(raw) <= MAX_POLICY)
        _require(hashlib.sha256(raw).hexdigest() == expected_sha256)
        doc = decode_document(raw, MAX_POLICY)
        _require(set(doc) == {"schema", "authority_id", "deployment_domain", "issued_at",
                              "expires_at", "client_certificates", "approved_contexts",
                              "challenge_scopes"})
        _require(doc["schema"] == POLICY_SCHEMA)
        authority, domain = doc["authority_id"], doc["deployment_domain"]
        _require(_identity(authority) and _identity(domain) and authority != domain)
        issued, expires = doc["issued_at"], doc["expires_at"]
        _require(type(issued) is int and type(expires) is int
                 and 0 < issued < expires < (1 << 63) and expires-issued <= _MAX_POLICY_LIFETIME)
        def digests(values, limit, minimum):
            _require(type(values) is list and minimum <= len(values) <= limit)
            _require(all(_hex(v) for v in values) and len(set(values)) == len(values))
            return frozenset(values)
        certificates = digests(doc["client_certificates"], 64, 1)
        approvals = digests(doc["approved_contexts"], _MAX_APPROVALS, 0)
        scopes = doc["challenge_scopes"]
        _require(type(scopes) is list and 1 <= len(scopes) <= _MAX_SCOPES)
        keys = set(ChallengeScope.__dataclass_fields__)
        rows = []
        for row in scopes:
            _require(type(row) is dict and set(row) == keys)
            rows.append(ChallengeScope(**row))
        _require(len(set(rows)) == len(rows))
        result = cls(authority, domain, issued, expires, certificates,
                     approvals, frozenset(rows), expected_sha256)
        _require(result.active(int(time.time())))
        return result


class ReviewerPolicySigner:
    """Bounded replay custody and independently pinned decisions.

    Production executable requires a durable ledger. In-process fixtures may
    explicitly omit it and then have process-local custody only. Exhaustion
    denies instead of evicting replay history; no policy rotation resets it.
    """
    def __init__(self, policy, key, *, clock=time.time, replay_limit=_MAX_REPLAY, replay_ledger=None):
        _require(type(policy) is ReviewPolicy and isinstance(key, Ed25519PrivateKey))
        _require(type(replay_limit) is int and 1 <= replay_limit <= _MAX_REPLAY)
        self.policy, self._key, self._clock = policy, key, clock
        self._limit = replay_limit
        self._seen = set()
        if replay_ledger is not None:
            from scripts.independent_reviewer_replay import DurableReplayLedger
            _require(type(replay_ledger) is DurableReplayLedger
                     and replay_ledger.authority == policy.authority_id
                     and replay_ledger.domain == policy.deployment_domain)
        self._replay_ledger = replay_ledger
        self._lock = Lock()

    def _gate(self, client, nonce):
        _require(_hex(client) and client in self.policy.client_certificates)
        _require(type(nonce) is str and _NONCE.fullmatch(nonce) is not None)
        with self._lock:
            _require(self.policy.active(int(self._clock())))
            # Shared namespace across review and attestation: a nonce can
            # authorize exactly one operation in the current process.
            if self._replay_ledger is not None:
                self._replay_ledger.consume(nonce)
            else:
                _require(nonce not in self._seen and len(self._seen) < self._limit)
                self._seen.add(nonce)

    def review(self, raw, client):
        doc = decode_document(raw, MAX_REVIEW_BODY)
        _require(set(doc) == {"schema","nonce","context_sha256","untrusted_text"})
        _require(doc["schema"] == REVIEW_SCHEMA and _hex(doc["context_sha256"]))
        text = doc["untrusted_text"]
        _require(type(text) is str and 1 <= len(text) <= MAX_TEXT)
        try:
            payload = text.encode("utf-8", "strict")
        except UnicodeError:
            raise PolicyDenied("independent reviewer denied request") from None
        _require(1 <= len(payload) <= MAX_TEXT
                 and hashlib.sha256(payload).hexdigest() == doc["context_sha256"])
        self._gate(client, doc["nonce"])
        allowed = doc["context_sha256"] in self.policy.approved_contexts
        verdict = {
            "schema": VERDICT_SCHEMA, "nonce": doc["nonce"],
            "context_sha256": doc["context_sha256"], "reviewer_id": self.policy.authority_id,
            "allowed": allowed, "reason_code": "exact-approved" if allowed else "unreviewed-context",
        }
        _require(self.policy.active(int(self._clock())))
        verdict["signature"] = base64.b64encode(self._key.sign(VERDICT_DOMAIN + canonical(verdict))).decode("ascii")
        return canonical(verdict)

    def attest(self, raw, client):
        doc = decode_document(raw, MAX_ATTEST_BODY)
        scope_keys = set(ChallengeScope.__dataclass_fields__)
        _require(set(doc) == scope_keys | {"schema","nonce","epoch","authority_id","deployment_domain"})
        _require(doc["schema"] == ATTEST_SCHEMA and doc["authority_id"] == self.policy.authority_id
                 and doc["deployment_domain"] == self.policy.deployment_domain)
        epoch = doc["epoch"]
        _require(type(epoch) is int and 2 <= epoch < (1 << 63) and epoch % 2 == 0)
        scope = ChallengeScope(**{key: doc[key] for key in scope_keys})
        _require(scope in self.policy.challenge_scopes)
        # Sign only an exact known protocol challenge, not arbitrary bytes.
        _require(raw == canonical(doc))
        self._gate(client, doc["nonce"])
        _require(self.policy.active(int(self._clock())))
        return self._key.sign(raw)
