"""Publish only individually approved, exact-source original game packages.

The canonical GameWorkspace is the source/approval authority. This code reads
the published original sources, checks the original dual-runtime package
manifest, world/proof cross-identities and accepted source edit receipts,
then optionally returns a reproducible ZIP in memory. It does not run native
game binaries, grant new file writes, or certify a consumer release.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from hashlib import sha256
from io import BytesIO
import re
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from .contracts import canonical_digest
from .game_project_workspace import GameWorkspace, _json, _read
from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest

SCHEMA = "skeleton.ai.jeeves_release_custody.v1"
IDENT = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_PACKAGE = 2_200_000
MAX_SOURCE = 256_000
MAX_FILES = 16
MAX_ACCEPTED = 20_000
MAX_ACCEPTED_SCAN_BYTES = 8_000_000
REQUIRED_MEMBERS = frozenset((
    "index.html", "tile-editor.html",
    "godot/project.godot", "godot/export_presets.cfg",
    "godot/scenes/main.tscn", "godot/scripts/main.gd",
    "godot/world.json", "godot/proof.json",
    "README.md", "proof/verified_solution.json",
))


def _identifier(value, label):
    if type(value) is not str or not IDENT.fullmatch(value):
        raise JeevesAppwideError("invalid safe original " + label)
    return value


def _member(value):
    if (type(value) is not str or not 1 <= len(value) <= 280
            or "\\" in value or value.startswith("/")
            or any(p in ("", ".", "..") or p.startswith(".")
                   for p in value.split("/"))):
        raise JeevesAppwideError("unsafe or ambiguous source package member")
    return value


class JeevesReleaseCustody:
    """Release source verification and deterministic human-approved export."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("scanned application source inventory needed")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("canonical active original project needed")
        self.inv = inventory
        self.ws = workspace

    def _context(self, project, expected_snapshot=None):
        _identifier(project, "project")
        if project != self.ws.active():
            raise JeevesAppwideError("source release requires selected active project")
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("repository source inventory changed")
        return self.ws.tree()["revision"]

    def catalog(self, *, project, offset=0, limit=40,
                expected_snapshot=None):
        self._context(project, expected_snapshot)
        if type(offset) is not int or not 0 <= offset <= 50_000:
            raise JeevesAppwideError("bounded release offset expected")
        if type(limit) is not int or not 1 <= limit <= 80:
            raise JeevesAppwideError("bounded release page required")
        releases = set()
        for entry in self.ws.files("current", project):
            parts = entry.path.split("/")
            if (len(parts) >= 4 and parts[:2] == ["game", "releases"]
                    and IDENT.fullmatch(parts[2])):
                releases.add(parts[2])
        ordered = sorted(releases)
        page = ordered[offset:offset+limit]
        body = {
            "schema": SCHEMA + ".catalog",
            "project": project, "inventory_snapshot": self.inv._digest,
            "workspace_revision": self.ws.tree()["revision"],
            "total_source_release_ids": len(ordered),
            "offset": offset, "limit": limit,
            "release_ids": page,
            "next_offset": offset+len(page) if offset+len(page) < len(ordered) else None,
            "catalog_does_not_establish_package_completeness": True,
            "native_gameplay_or_device_executed": False,
        }
        return {**body, "digest": digest(body)}

    def _approved(self, project, desired):
        """Find source versions with actual canonical human-acceptance receipts.

        A historical acceptance is not current if the source bytes differ.
        An accepted receipt is an audit artifact, not a cryptographic signer.
        """
        folder = self.ws.root / "reviews" / "accepted"
        if folder.is_symlink() or not folder.is_dir():
            raise JeevesAppwideError("human acceptance source custody absent")
        files = sorted(folder.iterdir(), key=lambda p: p.name)
        if len(files) > MAX_ACCEPTED:
            raise JeevesAppwideError("accepted edit receipt inventory over budget")
        wanted = set(desired)
        approved = defaultdict(set)
        byte_total = 0
        for file in files:
            if not file.name.endswith(".json") or not SHA.fullmatch(file.stem):
                continue
            if file.is_symlink() or not file.is_file():
                raise JeevesAppwideError("unsafe accepted game source custody")
            size = file.stat().st_size
            byte_total += size
            if size > 5_000 or byte_total > MAX_ACCEPTED_SCAN_BYTES:
                raise JeevesAppwideError("review receipt scan exceeded safety budget")
            receipt = _json(_read(file, 5_000))
            if (type(receipt) is not dict
                    or receipt.get("schema") !=
                       "skeleton.game_builder.approved_targeted_edit.v1"
                    or receipt.get("proposal") != file.stem
                    or receipt.get("project") != project
                    or receipt.get("approved") is not True):
                continue
            path = receipt.get("path")
            checksum = receipt.get("result_sha256")
            if (path in wanted and type(checksum) is str
                    and SHA.fullmatch(checksum)):
                # The accepted record must correspond to a genuine canonical
                # *exact-source* review proposal. A stray editable receipt
                # with a matching SHA alone must not qualify a source release.
                proposed_path = (
                    self.ws.root / "reviews" / "proposals" /
                    (file.stem + ".json")
                )
                if (proposed_path.is_symlink() or
                        not proposed_path.is_file()):
                    continue
                try:
                    proposed = _json(_read(proposed_path, 300_000))
                except (ValueError, OSError):
                    continue
                if (type(proposed) is not dict
                        or canonical_digest(proposed) != file.stem
                        or proposed.get("schema") !=
                           "skeleton.game_builder.targeted_edit.v1"
                        or proposed.get("project") != project
                        or proposed.get("path") != path
                        or proposed.get("new_sha256") != checksum
                        or type(proposed.get("new_content")) is not str
                        or sha256(proposed["new_content"].encode()).hexdigest()
                           != checksum):
                    continue
                approved[path].add(checksum)
        return approved

    def _collect(self, *, project, release_id, expected_snapshot=None):
        revision = self._context(project, expected_snapshot)
        _identifier(release_id, "release")
        prefix = "game/releases/" + release_id + "/"
        all_paths = {
            file.path for file in self.ws.files("current", project)
            if file.path.startswith(prefix)
        }
        required_path = prefix + "release.json"
        if required_path not in all_paths:
            raise JeevesAppwideError("release has no reviewed canonical manifest source")
        release_bytes = self.ws.read("current", project, required_path)["content"].encode()
        manifest = _json(release_bytes.decode("utf-8"))
        if (type(manifest) is not dict or
                manifest.get("schema") !=
                "skeleton.game_builder.dual_runtime_package.v1"):
            raise JeevesAppwideError("unrecognized dual-runtime release manifest")
        manifest_copy = dict(manifest)
        declared_digest = manifest_copy.pop("manifest_digest", None)
        if (type(declared_digest) is not str or
                not SHA.fullmatch(declared_digest) or
                canonical_digest(manifest_copy) != declared_digest):
            raise JeevesAppwideError("original runtime release manifest digest drifted")
        if (manifest.get("project_id") != project or
                manifest.get("godot_hardware_tested") is not False or
                manifest.get("automatic_publication") is not False):
            raise JeevesAppwideError("release manifest owner or assurance claims invalid")
        files = manifest.get("files")
        if (type(files) is not dict or
                not REQUIRED_MEMBERS <= set(files)
                or not len(REQUIRED_MEMBERS) <= len(files) <= MAX_FILES - 1
                or any(type(key) is not str or type(val) is not str
                       or not SHA.fullmatch(val)
                       for key, val in files.items())):
            raise JeevesAppwideError("missing, extra, or invalid source package coverage")
        members = {_member(item) for item in files}
        if len(members) != len(files) or "release.json" in members:
            raise JeevesAppwideError("release manifest includes an invalid member")
        expected_paths = {prefix + item for item in members} | {required_path}
        if all_paths != expected_paths:
            raise JeevesAppwideError("original release files missing or unmanifested")
        if manifest.get("targets") != {
            "offline-html5": "source-rendered",
            "godot-4.2": "source-rendered-unexecuted",
        }:
            raise JeevesAppwideError("release source runtime declaration mismatched")
        data = {"release.json": release_bytes}
        total = len(release_bytes)
        revisions = {"release.json": sha256(release_bytes).hexdigest()}
        for name in sorted(members):
            path = prefix + name
            record = self.ws.read("current", project, path)
            content = record["content"].encode("utf-8")
            if (len(content) > MAX_SOURCE or
                    sha256(content).hexdigest() != files[name]):
                raise JeevesAppwideError("source file changed since native package manifest")
            total += len(content)
            if total > MAX_PACKAGE:
                raise JeevesAppwideError("approved game sources exceed export limit")
            data[name] = content
            revisions[name] = files[name]
        world = _json(data["godot/world.json"].decode("utf-8"))
        proof = _json(data["godot/proof.json"].decode("utf-8"))
        duplicate_proof = _json(data["proof/verified_solution.json"].decode("utf-8"))
        if (type(world) is not dict or type(proof) is not dict
                or world.get("schema") != "skeleton.game_builder.godot_world.v1"
                or proof.get("schema") != "skeleton.game_builder.solution_trace.v1"
                or duplicate_proof != proof
                or world.get("world_digest") != manifest.get("world_digest")
                or proof.get("world_digest") != manifest.get("world_digest")
                or proof.get("replay_digest") != manifest.get("proof_digest")
                or not isinstance(proof.get("final_state"), dict)
                or proof["final_state"].get("status") != "won"
                or not isinstance(world.get("intent"), dict)
                or world["intent"].get("project_id") != project):
            raise JeevesAppwideError("original world and claimed gameplay proof disagree")
        acceptance = self._approved(project, expected_paths)
        uncovered = sorted(
            member for member, checksum in revisions.items()
            if checksum not in acceptance[prefix + member]
        )
        if uncovered:
            raise JeevesAppwideError(
                "release sources lack current independent human acceptance: "
                + ", ".join(uncovered[:8]))
        if self.ws.tree()["revision"] != revision:
            raise JeevesAppwideError("workspace changed during approved release inspection")
        report = {
            "schema": SCHEMA + ".verified",
            "project": project, "release_id": release_id,
            "repo_inventory_snapshot": self.inv._digest,
            "workspace_revision": revision,
            "package_manifest_digest": declared_digest,
            "source_file_count": len(data),
            "combined_source_bytes": total,
            "source_sha256": dict(sorted(revisions.items())),
            "world_digest": manifest["world_digest"],
            "proof_digest": manifest["proof_digest"],
            "original_winning_trace_declared_and_source_pinned": True,
            "gameplay_replay_reexecuted_during_this_verification": False,
            "all_sources_from_current_game_workspace": True,
            "all_source_versions_have_canonical_human_acceptance_receipts": True,
            "zip_archive_written_to_server_disk": False,
            "godot_executable_or_hardware_certified": False,
            "commercial_release_certified": False,
        }
        return {**report, "digest": digest(report)}, data

    def verify(self, *, project, release_id, expected_snapshot=None):
        report, _ = self._collect(
            project=project, release_id=release_id,
            expected_snapshot=expected_snapshot)
        return report

    def replay(self, *, project, release_id, expected_verification_digest,
               expected_snapshot=None, operator_authorized=False):
        """Rebuild the approved original game and execute its winning trace.

        This is real canonical Python gameplay execution on the inspected
        original source identity; it is not a repository CI test run nor
        proof that a Godot binary or browser was executed.
        """
        if operator_authorized is not True:
            raise PermissionError("designer authorization required for actual gameplay replay")
        if (type(expected_verification_digest) is not str
                or not SHA.fullmatch(expected_verification_digest)):
            raise JeevesAppwideError("expected current approved source digest required")
        verified, source = self._collect(
            project=project, release_id=release_id,
            expected_snapshot=expected_snapshot)
        if verified["digest"] != expected_verification_digest:
            raise JeevesAppwideError("approved game source changed before replay")
        from .playable_world import GameBuildIntent
        from .playable_compiler import compile_original_game
        from .dual_runtime_export import render_dual_runtime_package

        authored = _json(source["godot/world.json"].decode("utf-8"))
        settings = authored["intent"]
        if type(settings) is not dict or settings.get("project_id") != project:
            raise JeevesAppwideError("approved original game has invalid project intent")
        reconstructed = GameBuildIntent(**settings)
        if (reconstructed.levels > 3 or reconstructed.width > 25
                or reconstructed.height > 25
                or reconstructed.hazards_per_level > 10):
            raise JeevesAppwideError("source replay outside reviewed consumer runtime budget")
        executed = compile_original_game(reconstructed, authorized=True)
        rebuilt = render_dual_runtime_package(executed, authorized=True)
        if (executed.world.digest != verified["world_digest"]
                or executed.proof.digest != verified["proof_digest"]
                or executed.proof.final_state.status != "won"
                or rebuilt.manifest["manifest_digest"] !=
                   verified["package_manifest_digest"]):
            raise JeevesAppwideError("approved sources diverge from actually recompiled game")
        if set(rebuilt.files) != set(source):
            raise JeevesAppwideError("recompiled game package member set differs")
        inconsistent = [
            name for name in sorted(source)
            if rebuilt.files[name] != source[name]
        ]
        if inconsistent:
            raise JeevesAppwideError("accepted source bytes do not match canonical game compiler: "
                                     + ", ".join(inconsistent[:5]))
        body = {
            "schema": SCHEMA + ".replay",
            "project": project,
            "release_id": release_id,
            "source_verification_digest": verified["digest"],
            "actual_recompiled_world_digest": executed.world.digest,
            "actual_python_winning_replay_digest": executed.proof.digest,
            "actual_gameplay_steps": executed.proof.final_state.steps,
            "final_gameplay_status": executed.proof.final_state.status,
            "source_artifacts_regenerated": len(rebuilt.files),
            "every_byte_matches_original_approved_source": True,
            "original_browser_source_matches": True,
            "godot_source_matches": True,
            "gameplay_simulator_actually_executed": True,
            "godot_binary_actually_executed": False,
            "browser_executed": False,
            "native_or_commercial_release_certified": False,
            "source_files_modified": 0,
        }
        return {**body, "digest": digest(body)}

    def compare(self, *, project, release_ids,
                expected_snapshot=None):
        """Compare actual accepted game variants rather than enumerating imaginary ones."""
        self._context(project, expected_snapshot)
        if (type(release_ids) is not list or
                not 2 <= len(release_ids) <= 6 or
                any(type(item) is not str for item in release_ids) or
                len(release_ids) != len(set(release_ids))):
            raise JeevesAppwideError("2–6 unique original game release IDs required")
        accepted = []
        versions = []
        for release_id in sorted(release_ids):
            receipt, source = self._collect(
                project=project, release_id=release_id,
                expected_snapshot=expected_snapshot)
            accepted.append(receipt)
            versions.append(source)
        world_counts = {record["world_digest"] for record in accepted}
        names = sorted(set().union(*(set(source) for source in versions)))
        changes = []
        for filename in names:
            digests = [
                sha256(source[filename]).hexdigest()
                if filename in source else None
                for source in versions
            ]
            if len(set(digests)) > 1:
                changes.append({
                    "source_member": filename,
                    "per_release_sha256": dict(zip(sorted(release_ids), digests)),
                    "content_differs": True,
                })
        body = {
            "schema": SCHEMA + ".comparison",
            "project": project,
            "inventory_snapshot": self.inv._digest,
            "releases": [{
                "release_id": row["release_id"],
                "release_verification_digest": row["digest"],
                "world_digest": row["world_digest"],
                "proof_digest": row["proof_digest"],
                "source_files": row["source_file_count"],
            } for row in accepted],
            "distinct_real_worlds": len(world_counts),
            "all_selected_worlds_different": len(world_counts) == len(accepted),
            "source_member_total": len(names),
            "different_source_members": len(changes),
            "changed_members": changes,
            "each_source_had_a_human_acceptance_receipt": True,
            "no_untested_platform_equivalence_claim": True,
            "source_mutated": False,
        }
        return {**body, "digest": digest(body)}

    def download(self, *, project, release_id, expected_verification_digest,
                 expected_snapshot=None, operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("original game source export needs designer approval")
        if (type(expected_verification_digest) is not str
                or not SHA.fullmatch(expected_verification_digest)):
            raise JeevesAppwideError("source version-locked verification required")
        report, data = self._collect(
            project=project, release_id=release_id,
            expected_snapshot=expected_snapshot)
        if expected_verification_digest != report["digest"]:
            raise JeevesAppwideError("reviewed source bundle changed before download")
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_STORED, allowZip64=False) as archive:
            for name, payload in sorted(data.items()):
                info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_STORED
                info.external_attr = 0o644 << 16
                archive.writestr(info, payload)
        output = buffer.getvalue()
        if len(output) > MAX_PACKAGE + 8192:
            raise JeevesAppwideError("source ZIP exceeds bounded download limit")
        body = {
            "schema": SCHEMA + ".zip",
            "project": project, "release_id": release_id,
            "verification_digest": report["digest"],
            "zip_sha256": sha256(output).hexdigest(),
            "zip_bytes": len(output),
            "filename": project + "_" + release_id + "_source.zip",
            "base64": base64.b64encode(output).decode("ascii"),
            "package_source_files_individually_human_approved": True,
            "godot_binary_included": False,
            "native_or_consumer_release_certified": False,
            "source_exported_from_server_filesystem": False,
        }
        # Do not digest the entire base64 blob a second time unnecessarily.
        return {**body, "digest": digest({
            key: value for key, value in body.items() if key != "base64"
        })}
