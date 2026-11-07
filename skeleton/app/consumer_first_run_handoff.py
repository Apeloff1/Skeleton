"""Fail-closed handoff contract for source-only first-run replay evidence.

A successful replay cannot be promoted to laptop, installer, AI, or release
qualification without independent device and provenance evidence.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

SCHEMA = "skeleton.app.consumer_first_run_evidence.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
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
    holds = evidence.get("release_holds")
    if type(holds) is not list or not holds or any(type(h) is not str or not h for h in holds):
        raise FirstRunHandoffContractError("release holds must be explicit")
    if len(set(holds)) != len(holds):
        raise FirstRunHandoffContractError("duplicate release hold")
    observation = evidence.get("runtime_observation")
    if type(observation) is not dict or observation.get("posix_nofollow_available") is not True:
        raise FirstRunHandoffContractError("source custody observation absent")
