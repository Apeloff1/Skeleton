"""Installed, source-pinned local weight staging and read-only recovery review.

The staging command accepts one independently SHA-256-pinned JSON request
from stdin. It never discovers, downloads, executes or activates models.
Inspection commands require a previously provisioned cooperating slot and
do not create a store, lock or new policy. Output does not reveal paths.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, BinaryIO, Sequence, TextIO

from .flgb_model_runtime import (
    MAX_WEIGHT_BYTES, MAX_WEIGHT_SHARDS, ModelIdentity, WeightLoadPlan, WeightShard,
    canonical_bytes, require_digest,
)
from .weight_shard_store import WeightShardStore, WeightShardStoreError
from .weight_store_disk_owner import DiskAdmissionPolicy, WeightStoreDiskOwner
from .weight_store_recovery import (
    RecoveryReviewPolicy, acknowledge_weight_store_recovery, review_weight_store,
)
from .weight_store_scrub import (
    ScrubPolicy, advance_weight_scrub, require_completed_weight_scrub,
    start_weight_scrub, weight_scrub_status,
)

_MAX_REQUEST_BYTES = 16 * 1024**2
_MAX_OUTPUT_BYTES = 8 * 1024**2


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise WeightShardStoreError("duplicate staging request field")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise WeightShardStoreError("nonfinite staging request value")


def _exact(value: Any, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise WeightShardStoreError("invalid staging request fields")
    return value


@dataclass(frozen=True, slots=True)
class StageRequest:
    identity: ModelIdentity
    plan: WeightLoadPlan
    paths: tuple[Path, ...]
    request_sha256: str


def read_stage_request(stream: BinaryIO, *, request_sha256: str,
                       model_identity_sha256: str, plan_sha256: str) -> StageRequest:
    """Validate raw document and independent semantic identities before writes."""
    for name, pin in (("request", request_sha256), ("model identity", model_identity_sha256),
                      ("plan", plan_sha256)):
        require_digest(pin, name)
    raw = stream.read(_MAX_REQUEST_BYTES + 1)
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= _MAX_REQUEST_BYTES:
        raise WeightShardStoreError("staging request exceeds byte bounds")
    if sha256(raw).hexdigest() != request_sha256:
        raise WeightShardStoreError("staging request SHA mismatch")
    record = _exact(json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                               parse_constant=_constant),
                    {"schema", "identity", "shards", "expected_total_bytes", "source_paths"})
    if record["schema"] != "skeleton.weight-stage-request.v1":
        raise WeightShardStoreError("unsupported staging request schema")
    identity = ModelIdentity(**_exact(record["identity"], {
        "model_id", "revision", "architecture", "config_digest",
        "tokenizer_digest", "weights_digest",
    }))
    if identity.identity_digest != model_identity_sha256:
        raise WeightShardStoreError("independent model identity pin mismatch")
    raw_shards = record["shards"]
    raw_paths = record["source_paths"]
    if (type(raw_shards) is not list or not 1 <= len(raw_shards) <= MAX_WEIGHT_SHARDS
            or type(raw_paths) is not list or len(raw_paths) != len(raw_shards)):
        raise WeightShardStoreError("invalid staging shard or source count")
    shards = tuple(WeightShard(**_exact(row, {"index", "digest", "bytes", "source"}))
                   for row in raw_shards)
    plan = WeightLoadPlan(identity.identity_digest, shards, record["expected_total_bytes"])
    if plan.digest != plan_sha256:
        raise WeightShardStoreError("independent plan pin mismatch")
    paths = []
    for value in raw_paths:
        if (type(value) is not str or not 1 <= len(value) <= 4096
                or any(ord(char) < 32 for char in value)):
            raise WeightShardStoreError("invalid explicit local source path")
        path = Path(value)
        if not path.is_absolute():
            raise WeightShardStoreError("absolute local source path required")
        paths.append(path)
    return StageRequest(identity, plan, tuple(paths), request_sha256)


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cooperating offline weight store administration")
    parser.add_argument("command", choices=("stage", "inspect", "recovery-review", "acknowledge-recovery",
                                            "scrub-start", "scrub-step", "scrub-status", "scrub-check"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--maximum-store-bytes", type=int, required=True)
    parser.add_argument("--maximum-plan-bytes", type=int, default=MAX_WEIGHT_BYTES)
    parser.add_argument("--minimum-free-bytes", type=int, default=1024**3)
    parser.add_argument("--maximum-entries", type=int, default=1_000_000)
    parser.add_argument("--request-sha256")
    parser.add_argument("--model-identity-sha256")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--review-entries", type=int, default=100_000)
    parser.add_argument("--review-metadata-bytes", type=int, default=64 * 1024**2)
    parser.add_argument("--review-references", type=int, default=262_144)
    parser.add_argument("--review-details", type=int, default=256)
    parser.add_argument("--intent-sha256")
    parser.add_argument("--review-sha256")
    parser.add_argument("--maximum-verified-weight-bytes", type=int)
    parser.add_argument("--scrub-campaign-sha256")
    parser.add_argument("--scrub-prior-sha256")
    parser.add_argument("--scrub-total-bytes", type=int, default=MAX_WEIGHT_BYTES)
    parser.add_argument("--scrub-tranche-bytes", type=int, default=4 * 1024**3)
    parser.add_argument("--scrub-tranche-objects", type=int, default=64)
    parser.add_argument("--require-clean", action="store_true",
                        help="Exit 3 for a completed review containing anomalies")
    args = parser.parse_args(argv)
    output = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        if not args.store.is_absolute():
            raise WeightShardStoreError("absolute local store path required")
        policy = DiskAdmissionPolicy(args.maximum_store_bytes, args.minimum_free_bytes,
                                     args.maximum_entries)
        if not 1 <= args.maximum_plan_bytes <= MAX_WEIGHT_BYTES:
            raise WeightShardStoreError("invalid independent logical plan ceiling")
        pins = (args.request_sha256, args.model_identity_sha256, args.plan_sha256)
        recovery_pins = (args.intent_sha256, args.review_sha256, args.maximum_verified_weight_bytes)
        if args.command != "acknowledge-recovery" and any(value is not None for value in recovery_pins):
            raise WeightShardStoreError("recovery pins require acknowledge-recovery")
        if args.scrub_prior_sha256 is not None and args.command != "scrub-start":
            raise WeightShardStoreError("prior scrub pin requires scrub-start")
        if args.scrub_campaign_sha256 is not None and args.command not in ("scrub-step", "scrub-check"):
            raise WeightShardStoreError("active scrub pin requires scrub-step or scrub-check")
        if args.command in ("scrub-step", "scrub-check") and args.scrub_campaign_sha256 is None:
            raise WeightShardStoreError("exact scrub campaign SHA required")
        if args.command == "stage":
            if not all(value is not None for value in pins) or args.require_clean:
                raise WeightShardStoreError("stage requires three independent pins")
            incoming = stdin if stdin is not None else sys.stdin.buffer
            request = read_stage_request(
                incoming, request_sha256=pins[0],
                model_identity_sha256=pins[1], plan_sha256=pins[2],
            )
            # All request validation occurs before the writable store opens.
            if request.plan.expected_total_bytes > args.maximum_plan_bytes:
                raise WeightShardStoreError("logical plan exceeds explicit stage ceiling")
            store = WeightShardStore(args.store, maximum_bytes=args.maximum_plan_bytes)
            owner = WeightStoreDiskOwner(store, policy)
            key, receipt = owner.stage(request.identity, request.plan,
                                       dict(enumerate(request.paths)))
            body = {"schema": "skeleton.weight-stage-result.v1", "plan_digest": key,
                    "request_sha256": request.request_sha256,
                    "model_identity_digest": request.identity.identity_digest,
                    "disk_receipt": receipt, "model_activation": "not_performed"}
            result = {**body, "digest": sha256(canonical_bytes(body)).hexdigest()}
        else:
            if any(value is not None for value in pins):
                raise WeightShardStoreError("staging pins require stage command")
            if args.require_clean and args.command != "recovery-review":
                raise WeightShardStoreError("require-clean applies only to recovery-review")
            acknowledge = args.command == "acknowledge-recovery"
            if acknowledge and not all(value is not None for value in recovery_pins):
                raise WeightShardStoreError("acknowledge-recovery requires explicit evidence pins and verification ceiling")
            writable = acknowledge or args.command in ("scrub-start", "scrub-step")
            store = WeightShardStore(args.store, maximum_bytes=args.maximum_plan_bytes,
                                     read_only=not writable, create=False)
            owner = WeightStoreDiskOwner(store, policy, initialize=False)
            if args.command == "inspect":
                result = owner.inspect()
            elif args.command == "scrub-start":
                result = start_weight_scrub(owner, ScrubPolicy(
                    maximum_entries=args.review_entries,
                    maximum_manifest_bytes=args.review_metadata_bytes,
                    maximum_references=args.review_references,
                    maximum_total_bytes=args.scrub_total_bytes,
                ), prior_campaign_digest=args.scrub_prior_sha256)
            elif args.command == "scrub-step":
                result = advance_weight_scrub(
                    owner, campaign_digest=args.scrub_campaign_sha256,
                    maximum_objects=args.scrub_tranche_objects,
                    maximum_bytes=args.scrub_tranche_bytes,
                )
            elif args.command == "scrub-status":
                result = weight_scrub_status(owner)
            elif args.command == "scrub-check":
                result = require_completed_weight_scrub(owner, campaign_digest=args.scrub_campaign_sha256)
            else:
                review_policy = RecoveryReviewPolicy(
                    maximum_entries=args.review_entries,
                    maximum_metadata_bytes=args.review_metadata_bytes,
                    maximum_references=args.review_references,
                    maximum_details=args.review_details,
                )
                if acknowledge:
                    result = acknowledge_weight_store_recovery(
                        owner, intent_digest=recovery_pins[0], review_digest=recovery_pins[1],
                        maximum_verified_weight_bytes=recovery_pins[2], policy=review_policy,
                    )
                else:
                    result = review_weight_store(owner, review_policy)
        encoded = canonical_bytes(result)
        if len(encoded) > _MAX_OUTPUT_BYTES:
            raise WeightShardStoreError("administrative receipt exceeds byte bounds")
        output.write(encoded.decode("utf-8") + "\n")
        if args.command == "scrub-step" and result.get("status") in ("blocked", "larger_tranche_required"):
            return 3
        return 3 if args.require_clean and result.get("status") != "no_anomalies_observed" else 0
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, OSError) as exc:
        # Raw exception text can contain operator filesystem paths.
        errors.write("weight-store operation rejected: " + type(exc).__name__ + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
