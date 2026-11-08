"""Fail-closed handoff contract for source-only first-run replay evidence.

A successful replay cannot be promoted to laptop, installer, AI, or release
qualification without independent device and provenance evidence.
"""
from __future__ import annotations

import re

PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MANDATORY_HOLDS = frozenset({
    "NATIVE_DEVICE_QUALIFICATION_ABSENT",
    "INSTALLER_DEVICE_LIFECYCLE_UNQUALIFIED",
    "SIGNED_PACKAGE_CHAIN_UNATTESTED",
    "ORIGINAL_CONTENT_RIGHTS_UNCERTIFIED",
    "GUARDED_LOCAL_AI_END_TO_END_UNQUALIFIED",
    "PERSISTENT_NESTED_ASSET_CUSTODY_UNQUALIFIED",
})
from collections.abc import Mapping

SCHEMA = "skeleton.app.consumer_first_run_evidence.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
HOLD_TOKEN = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
OBSERVATION_KEYS = frozenset({"posix_nofollow_available", "operating_system", "machine", "python"})
# Unknown fields are forbidden: a consumer must not mistake injected claims for
# authenticated device, installer, signing or release evidence.
DIGEST_KEYS = frozenset({
    "manifest_sha256", "archive_sha256", "save_sha256", "receipt_sha256",
    "world_digest", "replay_digest", "installed_tree_snapshot_sha256",
})

REQUIRED_FALSE = (
    "native_device_qualified", "native_godot_executed",
    "windows_laptop_qualified", "installer_qualified",
    "guarded_local_ai_qualified", "package_signed",
    "rights_certified", "persistent_rollback_protection",
    "release_certified", "all_input_inodes_stable_during_inspection",
)
REQUIRED_TRUE = (
    "read_only", "installed_game_and_private_save_reexecuted",
    "root_and_evidence_inodes_stable_during_inspection",
    "nested_asset_inode_inventory_attested",
    "nested_asset_inode_snapshots_equal",
)


class FirstRunHandoffContractError(ValueError):
    """Untrusted source evidence cannot be used as a qualified handoff."""


def validate_source_only_handoff(evidence: Mapping[str, object]) -> None:
    """Validate the completed source replay receipt without mutating it.

    This is a boundary guard, not a signature, proof of device execution,
    or authorization to distribute the game.
    """
    if type(evidence) is not dict:
        raise FirstRunHandoffContractError("evidence must be a plain mapping")
    # Bound untrusted receipt complexity before iterating user-supplied fields.
    # This guard does not establish provenance or release qualification.
    if len(evidence) > 64 or any(type(key) is not str or len(key) > 96 for key in evidence):
        raise FirstRunHandoffContractError("unbounded evidence envelope")
    allowed = (frozenset({"schema", "status", "project_id", "action_count",
                         "release_holds", "runtime_observation", "files_published",
                         "source_level_replay_passes"}) | DIGEST_KEYS |
               frozenset(REQUIRED_FALSE) | frozenset(REQUIRED_TRUE))
    if set(evidence) != allowed:
        raise FirstRunHandoffContractError("unknown or missing evidence fields")
    if evidence.get("schema") != SCHEMA or evidence.get("status") != "source_level_first_run_replayed_release_blocked":
        raise FirstRunHandoffContractError("source-only handoff schema or state invalid")
    for name in REQUIRED_FALSE:
        if evidence.get(name) is not False:
            raise FirstRunHandoffContractError(f"unqualified claim: {name}")
    for name in REQUIRED_TRUE:
        if evidence.get(name) is not True:
            raise FirstRunHandoffContractError(f"missing source replay proof: {name}")
    if type(evidence.get("files_published")) is not int or evidence["files_published"] != 0:
        raise FirstRunHandoffContractError("inspection must not publish files")
    if type(evidence.get("source_level_replay_passes")) is not int or evidence["source_level_replay_passes"] != 2:
        raise FirstRunHandoffContractError("two source replays required")
    for name in ("manifest_sha256", "archive_sha256", "save_sha256",
                 "receipt_sha256", "world_digest", "replay_digest",
                 "installed_tree_snapshot_sha256"):
        if type(evidence.get(name)) is not str or SHA.fullmatch(evidence[name]) is None:
            raise FirstRunHandoffContractError(f"invalid digest: {name}")
    project_id = evidence.get("project_id")
    if type(project_id) is not str or PROJECT_ID.fullmatch(project_id) is None:
        raise FirstRunHandoffContractError("invalid canonical project identifier")
    action_count = evidence.get("action_count")
    if type(action_count) is not int or not 1 <= action_count <= 64:
        raise FirstRunHandoffContractError("invalid bounded replay action count")
    holds = evidence.get("release_holds")
    if (type(holds) is not list or not holds or len(holds) > 32
            or any(type(h) is not str or HOLD_TOKEN.fullmatch(h) is None for h in holds)):
        raise FirstRunHandoffContractError("release holds must be explicit")
    if not MANDATORY_HOLDS.issubset(holds):
        raise FirstRunHandoffContractError("mandatory release hold missing")
    if len(set(holds)) != len(holds):
        raise FirstRunHandoffContractError("duplicate release hold")
    observation = evidence.get("runtime_observation")
    if (type(observation) is not dict
            or set(observation) != OBSERVATION_KEYS
            or observation.get("posix_nofollow_available") is not True
            or type(observation.get("operating_system")) is not str
            or not observation["operating_system"]
            or len(observation["operating_system"]) > 64
            or type(observation.get("machine")) is not str
            or not observation["machine"]
            or len(observation["machine"]) > 64
            or type(observation.get("python")) is not str
            or re.fullmatch(r"\d+\.\d+\.\d+", observation["python"]) is None):
        raise FirstRunHandoffContractError("source custody observation absent")
