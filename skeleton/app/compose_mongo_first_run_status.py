"""Fail-closed evaluation of read-only Mongo observations for first-run UX.

This module deliberately cannot authorize guarded inference. The independent
activation gate must verify writer fencing, reviewer trust, and exact model
and tokenizer binding before admitting any request.
"""
from __future__ import annotations

from collections.abc import Mapping

# The only successful observation code. Every other code denotes incomplete or
# indeterminate custody, regardless of optimistic boolean flags.
COMPLETE_CODE = "mongo_epoch_observed_only"

REQUIRED_FIELDS = (
    "mongo_replica_set_primary_observed",
    "mongo_authenticated_session_observed",
    "canonical_actor_epoch_stable_observed",
    "canonical_database_name_aligned_observed",
)


def summarize_observation(observation: object) -> dict[str, object]:
    """Return a redacted, bounded status suitable for a first-run display.

    Never forward arbitrary strings from untrusted probes into UI or logs.
    An observation-only result is never an inference activation token.
    """
    from skeleton.app.compose_guarded_preflight import SCHEMA

    valid = (
        isinstance(observation, Mapping)
        and observation.get("schema_version") == SCHEMA
        and observation.get("writes_performed") is False
        and observation.get("guarded_local_ai_ready") is False
        and type(observation.get("code")) is str
        and all(type(observation.get(key)) is bool for key in REQUIRED_FIELDS)
    )
    checks = {
        key: bool(observation[key]) if valid else False
        for key in REQUIRED_FIELDS
    }
    return {
        "schema_version": "skeleton.app.compose_mongo_first_run_status.v1",
        "observation_valid": bool(valid),
        "checks": checks,
        "mongo_observation_complete": bool(\n            valid and observation.get("code") == COMPLETE_CODE and all(checks.values())\n        ),
        "guarded_local_ai_ready": False,
        "activation_permitted": False,
        "requires_independent_reviewer": True,
        "requires_writer_fencing": True,
        "requires_exact_model_tokenizer_binding": True,
    }
