"""Conservative pure predicates; no self-reported signal grants native start."""
from __future__ import annotations
from hmac import compare_digest
from .contracts import LaptopGateHold, StageVerdict, fingerprint, integer, name, sha

KINDS = frozenset(("true", "false", "sha_equal", "capacity", "bounded",
                   "fresh", "same_owner", "monotonic"))


def required_keys(kind: str, label: str) -> tuple[str, ...]:
    name(kind)
    name(label)
    if kind not in KINDS:
        raise LaptopGateHold("undeclared safeguard kind")
    mapping = {
        "true": ("verified",), "false": ("blocked",),
        "sha_equal": ("expected_sha256", "observed_sha256"),
        "capacity": ("available", "reserved"),
        "bounded": ("used", "limit"),
        "fresh": ("observed_at", "expires_at"),
        "same_owner": ("expected_owner", "active_owner"),
        "monotonic": ("previous", "current"),
    }
    return mapping[kind]


def _accept(kind: str, values: dict[str, object]) -> bool:
    if kind == "true":
        if type(values["verified"]) is not bool:
            raise LaptopGateHold("strict evidence boolean required")
        return values["verified"] is True
    if kind == "false":
        if type(values["blocked"]) is not bool:
            raise LaptopGateHold("strict denial boolean required")
        return values["blocked"] is False
    if kind == "sha_equal":
        return compare_digest(sha(values["expected_sha256"]),
                              sha(values["observed_sha256"]))
    if kind == "capacity":
        available = integer(values["available"])
        reserved = integer(values["reserved"])
        return 0 < reserved <= available
    if kind == "bounded":
        used = integer(values["used"])
        limit = integer(values["limit"])
        return limit > 0 and used <= limit
    if kind == "fresh":
        observed = integer(values["observed_at"], ceiling=4102444800)
        expires = integer(values["expires_at"], ceiling=4102444800)
        return observed < expires and expires - observed <= 86400
    if kind == "same_owner":
        return compare_digest(name(values["expected_owner"]),
                              name(values["active_owner"]))
    if kind == "monotonic":
        return integer(values["current"]) >= integer(values["previous"])
    raise LaptopGateHold("unknown safeguard kind")


def evaluate(kind: str, stage: str, evidence: object) -> StageVerdict:
    fields = required_keys(kind, stage)
    if type(evidence) is not dict or set(evidence) != set(fields):
        raise LaptopGateHold("wrong fields for named safeguard")
    accepted = _accept(kind, evidence)
    return StageVerdict(stage, accepted, "observed" if accepted else "held",
                        fingerprint({"kind": kind, "stage": stage,
                                     "evidence": evidence}))


def sample(kind: str) -> dict[str, object]:
    """An explicitly synthetic parser fixture; never device proof."""
    samples = {
        "true": {"verified": True},
        "false": {"blocked": False},
        "sha_equal": {"expected_sha256": "a"*64, "observed_sha256": "a"*64},
        "capacity": {"available": 4096, "reserved": 512},
        "bounded": {"used": 2, "limit": 8},
        "fresh": {"observed_at": 100, "expires_at": 200},
        "same_owner": {"expected_owner": "local", "active_owner": "local"},
        "monotonic": {"previous": 1, "current": 2},
    }
    if kind not in samples:
        raise LaptopGateHold("unknown sample contract")
    return dict(samples[kind])
