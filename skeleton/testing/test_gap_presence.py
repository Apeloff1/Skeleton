"""Presence verification for the multi-gap starter packet."""
import importlib

MODULES = [
    "skeleton.security.path_url_hardener",
    "skeleton.forge.pipelines.commercial_asset_starter",
    "skeleton.distributed.mesh.multiplayer_authority",
    "skeleton.knowledge.graphs.sheaf_facade",
    "skeleton.native.emulation_mapping",
    "skeleton.ai.runtime.weight_candidate_loop",
    "skeleton.simulation.platform.visual_verification",
    "skeleton.simulation.game.driving_kinematic",
    "skeleton.foundation.architecture.genos_cutover",
    "skeleton.repo_machine.shim_audit",
    "skeleton.app.gap_orchestrator",
    "skeleton.app.gap_cli",
    "skeleton.app.gap_status",
    "skeleton.app.gap_health",
    "skeleton.app.gap_metrics",
    "skeleton.app.gap_routes",
    "skeleton.app.gap_probe",
    "skeleton.app.gap_ci",
    "skeleton.app.gap_evidence",
    "skeleton.app.gap_ready",
    "skeleton.app.gap_seal",
]

def test_all_modules_import():
    for mod in MODULES:
        importlib.import_module(mod)
