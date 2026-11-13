"""Release-readiness diagnostic schema, never actual release authorization.

All eight source observations and their aggregate model pairing must
agree. Independently successful security, rights, physical device and
exact-head native checks are mandatory separately: a green synthetic
source fixture never establishes their results or permits promotion.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    release_model,
    installed_model,
    release_owner,
    rights_review,
    security_checks,
    device_report,
    latest_revision,
    revoked,
)

DOMAIN = "release_gates"
STAGES = ("release_model", "installed_model", "release_owner", "rights_review", "security_checks", "device_report", "latest_revision", "revoked",)
STAGE_TYPES = (("release_model", "sha_equal"), ("installed_model", "sha_equal"), ("release_owner", "same_owner"), ("rights_review", "true"), ("security_checks", "true"), ("device_report", "true"), ("latest_revision", "monotonic"), ("revoked", "false"),)
HANDLERS = (release_model, installed_model, release_owner, rights_review, security_checks, device_report, latest_revision, revoked,)


def evaluate(e: object):
    """Deny missing/extra release gates and inconsistent model identifiers."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("incomplete source-only release gate inventory")
    rows = tuple(module.check(e[name])
                 for name,module in zip(STAGES,HANDLERS))
    if len(rows) != 8 or len({v.stage for v in rows}) != 8:
        raise LaptopGateHold("release safeguard roster incomplete")
    if all(row.accepted for row in rows):
        if e["release_model"]["observed_sha256"] != e["installed_model"]["observed_sha256"]:
            raise LaptopGateHold("release source and installed model do not match")
    return rows


def contracts() -> tuple[dict[str, object], ...]:
    """Source diagnostic contracts are not release certificates."""
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["STAGES", "STAGE_TYPES", "evaluate", "contracts"]
