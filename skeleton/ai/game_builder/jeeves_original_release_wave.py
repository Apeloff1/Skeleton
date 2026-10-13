"""Generate genuine original browser/Godot game sources for reviewed Studio custody.

The existing game compiler produces actual deterministic gameplay and a Python
winning replay. The canonical exporter renders an offline browser game and
Godot project source; this adapter ties their bytes to the selected user's
GameWorkspace proposal/commit protocol rather than manufacturing a new
publisher. Godot binary execution and commercial release are not certified.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re
from typing import Any

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .game_project_workspace import GameWorkspace
from .playable_world import GameBuildIntent
from .playable_compiler import compile_original_game
from .dual_runtime_export import render_dual_runtime_package

SCHEMA = "skeleton.ai.jeeves_original_release_wave.v1"
EMPTY_SHA = sha256(b"").hexdigest()
IDENT = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
MAX_PACKAGE_BYTES = 1_800_000
MAX_FILES = 16
MAX_INDIVIDUAL_BYTES = 245_000
MAX_REASON = 1000
INTENT_KEYS = frozenset({
    "title", "subtitle", "seed", "width", "height", "levels",
    "collectibles_per_level", "hazards_per_level", "theme",
    "starting_health",
})
REQUIRED_KEYS = frozenset({"title", "subtitle", "seed"})


class JeevesOriginalReleaseWave:
    """Reviewable game output built from the actual installed game compiler."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("source-custodied app inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("canonical original GameWorkspace required")
        self.inv = inventory
        self.ws = workspace

    def _assemble(self, *, project: Any, release_id: Any,
                  intent: Any, expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale repository inventory")
        if type(project) is not str or not IDENT.fullmatch(project):
            raise JeevesAppwideError("safe original project ID required")
        if type(release_id) is not str or not IDENT.fullmatch(release_id):
            raise JeevesAppwideError("safe original release ID required")
        if self.ws.active() != project:
            raise JeevesAppwideError("release must target the selected current project")
        if (type(intent) is not dict or
                set(intent) - INTENT_KEYS or
                not REQUIRED_KEYS <= set(intent)):
            raise JeevesAppwideError("exact bounded game intent fields required")
        build = GameBuildIntent(project_id=project, **intent)
        # Respect the same finite synchronous Jeeves budget used by the
        # canonical single original-game compiler adapter.
        if (build.levels > 3 or build.width > 25 or
                build.height > 25 or build.hazards_per_level > 10):
            raise JeevesAppwideError(
                "reviewed synchronous game compilation budget exceeded")
        compiled = compile_original_game(build, authorized=True)
        package = render_dual_runtime_package(compiled, authorized=True)
        files = sorted(package.files.items())
        if len(files) > MAX_FILES:
            raise JeevesAppwideError("too many native/browser source files")
        total = sum(len(contents) for _, contents in files)
        if total > MAX_PACKAGE_BYTES:
            raise JeevesAppwideError("combined game export exceeds bounded budget")
        existing = {entry.path: entry for entry in
                    self.ws.files("current", project)}
        planned = []
        sources = []
        for filename, payload in files:
            if not isinstance(payload, bytes) or len(payload) > MAX_INDIVIDUAL_BYTES:
                raise JeevesAppwideError("unsupported or oversized source artifact")
            if (filename.startswith("/") or "\\" in filename or
                    any(x in ("", ".", "..") for x in filename.split("/"))):
                raise JeevesAppwideError("native package path is not safely contained")
            path = "game/releases/" + release_id + "/" + filename
            # Do not bypass the GameWorkspace source/extension allow-list.
            self.ws._file("current", project, path)
            try:
                text = payload.decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise JeevesAppwideError(
                    "reviewed game workspace only supports UTF-8 source packages"
                ) from exc
            checksum = sha256(payload).hexdigest()
            if path in existing:
                before = self.ws.read("current", project, path)
                previous_sha = before["version"]["sha256"]
            else:
                previous_sha = EMPTY_SHA
            unchanged = previous_sha == checksum and path in existing
            row = {
                "path": path,
                "package_member": filename,
                "source_bytes": len(payload),
                "previous_sha256": previous_sha,
                "candidate_sha256": checksum,
                "unchanged": unchanged,
                "human_commit_required": True,
            }
            planned.append(row)
            sources.append((row, text))
        receipt = {
            "schema": SCHEMA + ".plan",
            "project": project,
            "release_id": release_id,
            "intent": build.to_payload(),
            "inventory_snapshot": self.inv._digest,
            "workspace_revision": self.ws.tree()["revision"],
            "world_digest": compiled.world.digest,
            "gameplay_proof_digest": compiled.proof.digest,
            "proof_status": compiled.proof.final_state.status,
            "browser_html_sha256": compiled.playable.html_sha256,
            "package_manifest_digest": package.manifest["manifest_digest"],
            "source_target_count": len(planned),
            "changed_source_count": sum(not item["unchanged"] for item in planned),
            "package_source_bytes": total,
            "targets": planned,
            "real_original_game_compiler_ran": True,
            "python_winning_replay_executed_by_game_compiler": True,
            "offline_browser_source_rendered": True,
            "godot_source_rendered": True,
            "godot_binary_ran": False,
            "native_release_certified": False,
            "all_sources_require_independent_review": True,
            "source_files_committed": 0,
            "runtime_files_written": 0,
            "external_provider_used": False,
        }
        return {**receipt, "digest": digest(receipt)}, sources

    def plan(self, *, project, release_id, intent,
             expected_snapshot=None, operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("original game compilation needs designer approval")
        result, _ = self._assemble(
            project=project, release_id=release_id, intent=intent,
            expected_snapshot=expected_snapshot)
        return result

    def stage(self, *, project, release_id, intent,
              expected_plan_digest, reason,
              expected_snapshot=None, operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("native game source staging needs designer approval")
        if (type(expected_plan_digest) is not str or
                not re.fullmatch(r"[0-9a-f]{64}", expected_plan_digest)):
            raise JeevesAppwideError("exact source-release plan identity required")
        if (type(reason) is not str or "\x00" in reason or
                not 12 <= len(reason) <= MAX_REASON):
            raise JeevesAppwideError("specific designer release review reason required")
        receipt, files = self._assemble(
            project=project, release_id=release_id, intent=intent,
            expected_snapshot=expected_snapshot)
        if receipt["digest"] != expected_plan_digest:
            raise JeevesAppwideError("release source drifted after reviewed plan")
        if not receipt["changed_source_count"]:
            raise JeevesAppwideError("every release source already matches current project")
        proposals = []
        # A source proposal is a durable review record, not a committed file.
        # Source edits remain individually approved through Workspace.commit.
        for target, source in files:
            if target["unchanged"]:
                continue
            proposal = self.ws.propose(
                project, target["path"], source,
                expected_sha256=target["previous_sha256"],
                reason=reason, authorized=True)
            proposals.append({
                "path": target["path"],
                "proposal_id": proposal["proposal_id"],
                "sha256": target["candidate_sha256"],
                "committed": False,
            })
        body = {
            "schema": SCHEMA + ".staged",
            "plan_digest": receipt["digest"],
            "project": project, "release_id": release_id,
            "package_manifest_digest": receipt["package_manifest_digest"],
            "proposals": proposals,
            "proposal_count": len(proposals),
            "proposals_require_individual_human_approval": True,
            "source_files_committed": 0,
            "export_directory_published": False,
            "godot_binary_executed": False,
            "commercial_release_certified": False,
        }
        return {**body, "digest": digest(body)}
