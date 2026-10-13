"""Actual reviewed Universal Forge source authoring for original Game Studio.

This is a source-binding layer over the installed Forge registry and existing
GameWorkspace, not a new forge engine. Component/kind and port validity are
checked both at proposal and again during human source commit.
"""
from __future__ import annotations

from hashlib import sha256
import re

from .contracts import canonical_json, canonical_digest
from .game_project_workspace import GameWorkspace
from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_app_runtime import _review_forge_graph

SCHEMA = "skeleton.ai.jeeves_forge_production.v1"
BLUEPRINT = "skeleton.game_builder.reviewed_forge_source.v1"
IDENT = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
EMPTY_SHA = sha256(b"").hexdigest()


class JeevesForgeProduction:
    """Validate, source-propose and inspect real original Forge component graphs."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("source-pinned application inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("selected canonical original game workspace required")
        self.inv = inventory
        self.ws = workspace

    def _prepare(self, *, project, blueprint_id, name, components, wires,
                 expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale repository inventory")
        if type(project) is not str or self.ws.active() != project:
            raise JeevesAppwideError("active original project required")
        if type(blueprint_id) is not str or not IDENT.fullmatch(blueprint_id):
            raise JeevesAppwideError("safe original Forge blueprint ID required")
        graph = _review_forge_graph({
            "name": name,
            "components": components,
            "wires": wires,
        })
        if not graph["valid"]:
            raise JeevesAppwideError(
                "actual Universal Forge graph validation failed: " +
                ", ".join(map(str, graph["problems"][:8])))
        source = {
            "schema": BLUEPRINT,
            "id": blueprint_id,
            "name": name,
            "components": components,
            "wires": wires,
            "review_digest": graph["digest"],
        }
        source = {**source, "digest": canonical_digest(source)}
        location = "assets/forge/" + blueprint_id + ".json"
        self.ws._validate_forge_blueprint(location, source)
        content = canonical_json(source) + "\n"
        if len(content.encode("utf-8")) > 128_000:
            raise JeevesAppwideError("original Forge graph source exceeds authoring budget")
        prior = {file.path: file for file in self.ws.files("current", project)}
        current = prior.get(location)
        previous = current.sha256 if current is not None else EMPTY_SHA
        candidate = sha256(content.encode("utf-8")).hexdigest()
        body = {
            "schema": SCHEMA + ".plan",
            "project": project,
            "blueprint_id": blueprint_id,
            "path": location,
            "repo_inventory_snapshot": self.inv._digest,
            "workspace_revision": self.ws.tree()["revision"],
            "source_before_sha256": previous,
            "source_after_sha256": candidate,
            "original_blueprint_digest": source["digest"],
            "canonical_installed_forge_graph_review": graph,
            "original_forge_document": source,
            "source_bytes": len(content.encode("utf-8")),
            "already_committed_identically": (
                current is not None and previous == candidate),
            "actual_component_kinds_and_wire_ports_checked": True,
            "real_game_studio_source_not_committed_yet": True,
            "gameplay_render_or_asset_executable_not_claimed": True,
        }
        return {**body, "digest": digest(body)}, content

    def plan(self, *, project, blueprint_id, name, components, wires,
             expected_snapshot=None):
        report, _ = self._prepare(
            project=project, blueprint_id=blueprint_id,
            name=name, components=components, wires=wires,
            expected_snapshot=expected_snapshot)
        return report

    def stage(self, *, project, blueprint_id, name, components, wires,
              expected_plan_digest, reason,
              expected_snapshot=None, operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer must approve actual original Forge source changes")
        if (type(expected_plan_digest) is not str or
                not SHA.fullmatch(expected_plan_digest)):
            raise JeevesAppwideError("exact reviewed Forge source plan required")
        if type(reason) is not str or not 12 <= len(reason) <= 1000:
            raise JeevesAppwideError("bounded specific Forge review reason required")
        report, content = self._prepare(
            project=project, blueprint_id=blueprint_id,
            name=name, components=components, wires=wires,
            expected_snapshot=expected_snapshot)
        if report["digest"] != expected_plan_digest:
            raise JeevesAppwideError("Forge blueprint changed after designer review")
        if report["already_committed_identically"]:
            raise JeevesAppwideError("current approved Forge blueprint already matches")
        proposed = self.ws.propose(
            project, report["path"], content,
            expected_sha256=report["source_before_sha256"],
            reason=reason, authorized=True)
        body = {
            "schema": SCHEMA + ".staged",
            "project": project,
            "blueprint_id": blueprint_id,
            "path": report["path"],
            "proposal_id": proposed["proposal_id"],
            "source_before_sha256": report["source_before_sha256"],
            "source_after_sha256": report["source_after_sha256"],
            "source_plan_digest": report["digest"],
            "installed_forge_review_digest": report[
                "canonical_installed_forge_graph_review"]["digest"],
            "source_files_committed": 0,
            "requires_exact_human_diff_review_and_source_commit": True,
            "unreviewed_forge_execution_performed": False,
        }
        return {**body, "digest": digest(body)}

    def verify(self, *, project, blueprint_id, expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale source inventory")
        if type(project) is not str or project != self.ws.active():
            raise JeevesAppwideError("selected active original project required")
        if type(blueprint_id) is not str or not IDENT.fullmatch(blueprint_id):
            raise JeevesAppwideError("safe Forge blueprint ID required")
        location = "assets/forge/" + blueprint_id + ".json"
        from .game_project_workspace import _json
        source = self.ws.read("current", project, location)
        check = self.ws._validate_forge_blueprint(
            location, _json(source["content"]))
        body = {
            "schema": SCHEMA + ".verified",
            "project": project, "path": location,
            "current_source_sha256": source["version"]["sha256"],
            "canonical_validation": check,
            "installed_port_graph_validated": True,
            "runtime_game_asset_execution_proven": False,
            "source_mutated": False,
        }
        return {**body, "digest": digest(body)}
