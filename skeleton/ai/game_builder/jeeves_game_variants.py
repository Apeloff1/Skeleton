"""Render multiple DISTINCT genuine original browser and Godot game candidates.

Uses the same canonical single-game compiler, proof, source renderer and
human-reviewed GameWorkspace proposals. No hypothetical generated games,
runtime provider, extra repository writer, or native binary certification.
"""
from __future__ import annotations

from hashlib import sha256
import re

from .game_project_workspace import GameWorkspace
from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_original_release_wave import JeevesOriginalReleaseWave
from .playable_world import GameBuildIntent

SCHEMA = "skeleton.ai.jeeves_game_variants.v1"
THEMES = ("forest", "space", "desert", "ocean", "arcade")
PREFIX = re.compile(r"[a-z][a-z0-9_-]{1,47}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_VARIANTS = 4
MAX_TOTAL_SOURCE = 6_000_000


class JeevesGameVariants:
    """Finite multi-game design/production plans with independent source custody."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical source inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("canonical GameWorkspace required")
        self.inv = inventory
        self.ws = workspace

    def _arguments(self, project, release_prefix, base_intent, count,
                   seed_step, rotate_themes):
        if (type(project) is not str or self.ws.active() != project
                or type(release_prefix) is not str
                or not PREFIX.fullmatch(release_prefix)):
            raise JeevesAppwideError("selected project and safe release prefix required")
        if type(count) is not int or not 1 <= count <= MAX_VARIANTS:
            raise JeevesAppwideError("1–4 original variants required")
        if type(seed_step) is not int or not 1 <= seed_step <= 1_000_000:
            raise JeevesAppwideError("bounded nonzero seed step required")
        if type(rotate_themes) is not bool:
            raise JeevesAppwideError("typed theme rotation flag required")
        if type(base_intent) is not dict:
            raise JeevesAppwideError("typed original game intent required")
        allowed = frozenset({
            "title", "subtitle", "seed", "width", "height", "levels",
            "collectibles_per_level", "hazards_per_level", "theme",
            "starting_health",
        })
        if set(base_intent) - allowed or not {"title", "subtitle", "seed"} <= set(base_intent):
            raise JeevesAppwideError("unrecognized or absent game intent fields")
        first = GameBuildIntent(project_id=project, **base_intent)
        if first.seed + (count - 1) * seed_step > 2**63 - 1:
            raise JeevesAppwideError("derived original seeds exceed bounds")
        jobs = []
        origin_theme = THEMES.index(first.theme)
        for number in range(count):
            intent = first.to_payload()
            intent.pop("project_id")
            intent["seed"] = first.seed + number * seed_step
            if rotate_themes:
                intent["theme"] = THEMES[(origin_theme + number) % len(THEMES)]
            release_id = release_prefix + "_%02d" % (number + 1)
            if len(release_id) > 64:
                raise JeevesAppwideError("derived original release ID too long")
            jobs.append({"project": project, "release_id": release_id, "intent": intent})
        return jobs

    def _plans(self, *, project, release_prefix, base_intent, count=2,
               seed_step=1009, rotate_themes=True, expected_snapshot=None,
               operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer approval required for compiled original games")
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("source inventory changed")
        jobs = self._arguments(
            project, release_prefix, base_intent, count, seed_step, rotate_themes)
        builder = JeevesOriginalReleaseWave(self.inv, self.ws)
        variants, seen = [], set()
        total = 0
        for job in jobs:
            outcome = builder.plan(
                **job, expected_snapshot=expected_snapshot,
                operator_authorized=True)
            if outcome["world_digest"] in seen:
                raise JeevesAppwideError("seeded variants duplicate the same game world")
            seen.add(outcome["world_digest"])
            total += outcome["package_source_bytes"]
            if total > MAX_TOTAL_SOURCE:
                raise JeevesAppwideError("game portfolio exceeds source budget")
            variants.append({
                "release_id": job["release_id"],
                "intent": job["intent"],
                "world_digest": outcome["world_digest"],
                "winning_replay_digest": outcome["gameplay_proof_digest"],
                "manifest_digest": outcome["package_manifest_digest"],
                "original_source_plan_digest": outcome["digest"],
                "source_file_count": outcome["source_target_count"],
                "changed_source_file_count": outcome["changed_source_count"],
                "source_bytes": outcome["package_source_bytes"],
                "godot_runtime_executed": False,
            })
        body = {
            "schema": SCHEMA + ".plan",
            "project": project,
            "source_inventory": self.inv._digest,
            "workspace_revision": self.ws.tree()["revision"],
            "variant_count": len(variants),
            "source_file_count": sum(v["source_file_count"] for v in variants),
            "source_bytes": total,
            "variants": variants,
            "actually_distinct_world_hashes": True,
            "real_original_game_compiler_and_python_replay_used": True,
            "game_source_files_committed": 0,
            "human_game_source_review_required": True,
        }
        return {**body, "digest": digest(body)}, jobs

    def plan(self, *, project, release_prefix, base_intent, count=2,
             seed_step=1009, rotate_themes=True, expected_snapshot=None,
             operator_authorized=False):
        receipt, _ = self._plans(
            project=project, release_prefix=release_prefix,
            base_intent=base_intent, count=count, seed_step=seed_step,
            rotate_themes=rotate_themes, expected_snapshot=expected_snapshot,
            operator_authorized=operator_authorized)
        return receipt

    def stage(self, *, project, release_prefix, base_intent,
              expected_portfolio_digest, reason, count=2, seed_step=1009,
              rotate_themes=True, expected_snapshot=None, operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("portfolio source staging needs designer approval")
        if type(expected_portfolio_digest) is not str or not SHA.fullmatch(expected_portfolio_digest):
            raise JeevesAppwideError("source-bound portfolio plan digest required")
        if type(reason) is not str or not 12 <= len(reason) <= 1000:
            raise JeevesAppwideError("specific source review reason required")
        plan, jobs = self._plans(
            project=project, release_prefix=release_prefix,
            base_intent=base_intent, count=count, seed_step=seed_step,
            rotate_themes=rotate_themes, expected_snapshot=expected_snapshot,
            operator_authorized=True)
        if plan["digest"] != expected_portfolio_digest:
            raise JeevesAppwideError("portfolio source identity changed before staging")
        builder = JeevesOriginalReleaseWave(self.inv, self.ws)
        outputs = []
        for index, job in enumerate(jobs):
            try:
                staged = builder.stage(
                    **job,
                    expected_plan_digest=plan["variants"][index]["original_source_plan_digest"],
                    reason=reason, expected_snapshot=expected_snapshot,
                    operator_authorized=True)
            except (ValueError, OSError) as exc:
                partial = {
                    "schema": SCHEMA + ".partial",
                    "portfolio_digest": plan["digest"],
                    "staged_variants": outputs,
                    "remaining_release_ids": [
                        row["release_id"] for row in plan["variants"][index:]
                    ],
                    "error_class": type(exc).__name__,
                    "partial_review_staging_not_source_commit": True,
                    "rerun_requires_fresh_review": True,
                }
                return {**partial, "digest": digest(partial)}
            outputs.append({
                "release_id": job["release_id"],
                "proposals": staged["proposals"],
                "proposal_count": staged["proposal_count"],
            })
        result = {
            "schema": SCHEMA + ".staged",
            "project": project, "portfolio_digest": plan["digest"],
            "variant_count": len(outputs), "variants": outputs,
            "proposal_count": sum(row["proposal_count"] for row in outputs),
            "source_files_committed": 0,
            "independent_human_file_commit_required": True,
            "consumer_release_certified": False,
        }
        return {**result, "digest": digest(result)}
