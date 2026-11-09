"""
Skeleton — Round-6 architecture addendum

Godot verify-loop round: organism paths, forge polish loop,
emit→verify end-to-end coverage, quality ledger wiring.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.organism.paths": {
        "layer": "organism",
        "purpose": "Single source of truth for organism state files (policy.json, quality.jsonl)",
        "exports": ["organism_dir", "quality_path"],
    },
    "skeleton.forge.forge_quality": {
        "layer": "forge",
        "purpose": "Bounded polish loop composing scoring with optional file repair",
        "exports": ["polish_loop"],
    },
}

VERIFY_CHAIN = [
    "emit_godot → files",
    "gdscript_check.check_files → project closure proof",
    "ForgeVerifier.verify → accept/reject + quality report",
    "CodeVerifier.verdict → rubric confidence",
    "VerificationLoop → bounded revise-until-green",
    "attempt_repair → targeted script/project patches",
    "append_quality → JSONL quality ledger",
]


def summary() -> Dict[str, Any]:
    return {
        "round6_modules": len(NEW_MODULES),
        "verify_chain_stages": len(VERIFY_CHAIN),
        "verify_chain": VERIFY_CHAIN,
        "godot_targets_verified": ["static check", "verifier accept", "loop until green", "repair materialise"],
    }
