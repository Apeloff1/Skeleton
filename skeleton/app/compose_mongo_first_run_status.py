"""Fail-closed evaluation of read-only Mongo observations for first-run UX.

This module deliberately cannot authorize guarded inference. The independent
activation gate must verify writer fencing, reviewer trust, and exact model
and tokenizer binding before admitting any request.
"""
from __future__ import annotations

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
        type(observation) is dict
        and len(observation) <= 32
        # Check exact key types before any dictionary lookup can invoke a
        # colliding hostile key's __eq__ callback.
        and all(type(key) is str and len(key) <= 128 for key in observation)
        and type(observation.get("schema_version")) is str
        and observation["schema_version"] == SCHEMA
        and observation.get("writes_performed") is False
        and observation.get("guarded_local_ai_ready") is False
        and observation.get("activation_permitted", False) is False
        and observation.get("independent_reviewer_verified", False) is False
        and observation.get("canonical_writer_inventory_verified", False) is False
        and observation.get("activated_model_tokenizer_verified", False) is False
        and observation.get("canonical_cluster_identity_verified", False) is False
        and observation.get("consumer_or_device_qualified", False) is False
        and type(observation.get("code")) is str
        and len(observation["code"]) <= 128
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
        "mongo_observation_complete": bool(
            valid and observation.get("code") == COMPLETE_CODE and all(checks.values())
        ),
        "guarded_local_ai_ready": False,
        "activation_permitted": False,
        "requires_independent_reviewer": True,
        "requires_writer_fencing": True,
        "requires_exact_model_tokenizer_binding": True,
    }

# Public reason codes only; unknown probe output cannot be reflected to the
# console, even when it fits the structural observation envelope.
_OPERATOR_CODES = frozenset({
    "operator_actor_scope_required", "mongo_authority_unavailable",
    "mongo_primary_probe_unavailable", "mongo_replica_set_primary_required",
    "mongo_authenticated_session_unavailable", "mongo_authenticated_session_required",
    "mongo_primary_changed_during_preflight", "mongo_principal_changed_during_preflight",
    "canonical_actor_epoch_changed_during_preflight",
    "mongo_primary_changed_during_final_epoch_read",
    "mongo_principal_changed_during_final_epoch_read",
    "mongo_primary_changed_after_final_authentication",
    "canonical_actor_epoch_unavailable", "mongo_epoch_observed_only",
    "mongo_connection_configuration_required", "canonical_engine_database_identity_required",
    "canonical_database_identity_mismatch", "mongo_preflight_deadline_exceeded",
})


def operator_main() -> int:
    """Explicit observation, never a model-start, migration or readiness command."""
    import asyncio
    import json

    from skeleton.app.compose_guarded_preflight import _run_from_environment

    try:
        observation = asyncio.run(_run_from_environment())
    except Exception:
        observation = None
    status = summarize_observation(observation)
    reason = "observation_unavailable"
    if status["observation_valid"] is True:
        code = observation["code"]
        if code in _OPERATOR_CODES:
            reason = code
    status["observation_code"] = reason
    status["writes_performed"] = False
    status["consumer_or_device_qualified"] = False
    print(json.dumps(status, sort_keys=True, separators=(",", ":"), allow_nan=False))
    # Even a complete read-only observation is deliberately nonzero.
    return 2
