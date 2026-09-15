"""
services/registries/expansion_packs.py — EXPANSION_PACKS.

Extracted from server.py (Feb 2026 Phase-8). Pure data: expansion-pack
catalogue. References ``ExpansionCategory`` and ``ExpansionStatus`` enums
which still live in server.py — imported at top-level here. We accept
the import because EXPANSION_PACKS is only ever imported AFTER server.py
has fully loaded (via the shim line at the top of server.py).
"""
from __future__ import annotations


def _get_enums():
    from server import ExpansionCategory, ExpansionStatus  # noqa: PLC0415
    return ExpansionCategory, ExpansionStatus


# Construct the data at import time using the lazy enum accessor.
ExpansionCategory, ExpansionStatus = _get_enums()

# EXPANSION_PACKS references ALGORITHM_REGISTRY for its 'algorithms' pack —
# pull it in directly here (Phase-8 cross-module wiring).
from services.registries.algorithms import ALGORITHM_REGISTRY  # noqa: E402


EXPANSION_PACKS = {
    "systems_pro": {
        "id": "systems_pro",
        "name": "Systems Programming Pro",
        "category": ExpansionCategory.LANGUAGE,
        "description": "Complete systems programming toolkit",
        "languages": ["rust", "go", "zig", "nim", "crystal", "d", "v", "odin"],
        "features": ["memory_profiling", "unsafe_analysis", "ffi_generator"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "data_science": {
        "id": "data_science",
        "name": "Data Science Suite",
        "category": ExpansionCategory.LANGUAGE,
        "description": "Scientific computing and data analysis",
        "languages": ["julia", "r", "octave", "fortran", "wolfram"],
        "features": ["notebook_mode", "visualization", "data_import"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "mobile_dev": {
        "id": "mobile_dev",
        "name": "Mobile Development Kit",
        "category": ExpansionCategory.LANGUAGE,
        "description": "iOS, Android, and cross-platform development",
        "languages": ["swift", "kotlin", "dart", "objective_c"],
        "features": ["ui_preview", "device_simulation", "hot_reload"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "functional_pure": {
        "id": "functional_pure",
        "name": "Functional Programming Mastery",
        "category": ExpansionCategory.LANGUAGE,
        "description": "Pure functional languages",
        "languages": ["haskell", "ocaml", "f_sharp", "elixir", "erlang", "clojure", "elm", "purescript"],
        "features": ["type_inference_viewer", "monad_tutorials", "repl_enhanced"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "blockchain": {
        "id": "blockchain",
        "name": "Blockchain Development",
        "category": ExpansionCategory.LANGUAGE,
        "description": "Smart contract development",
        "languages": ["solidity", "vyper", "move"],
        "features": ["contract_testing", "gas_estimation", "security_audit"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "theorem_provers": {
        "id": "theorem_provers",
        "name": "Formal Methods & Proof Assistants",
        "category": ExpansionCategory.LANGUAGE,
        "description": "Theorem proving and formal verification",
        "languages": ["coq", "lean", "idris", "agda"],
        "features": ["proof_visualization", "tactic_hints", "theorem_search"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "compiler_internals": {
        "id": "compiler_internals",
        "name": "Compiler Internals Deep Dive",
        "category": ExpansionCategory.COMPILER,
        "description": "Low-level compilation analysis",
        "languages": ["assembly_x86", "assembly_arm", "webassembly", "llvm_ir"],
        "features": ["instruction_viewer", "pipeline_debugger", "binary_analysis"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "hardware_design": {
        "id": "hardware_design",
        "name": "Hardware Design Suite",
        "category": ExpansionCategory.LANGUAGE,
        "description": "HDL and hardware description",
        "languages": ["verilog", "vhdl", "chisel", "spinalhdl"],
        "features": ["waveform_viewer", "synthesis_preview", "timing_analysis"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "ai_ml_toolkit": {
        "id": "ai_ml_toolkit",
        "name": "AI/ML Integration Toolkit",
        "category": ExpansionCategory.AI,
        "description": "Multiple LLM providers and AI features",
        "providers": ["openai", "anthropic", "google", "grok"],
        "features": ["code_generation", "explanation", "refactoring", "test_generation"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
    "algorithm_explorer": {
        "id": "algorithm_explorer",
        "name": "Algorithm Explorer Pro",
        "category": ExpansionCategory.ALGORITHM,
        "description": "Interactive algorithm visualization",
        "algorithms": list(ALGORITHM_REGISTRY.keys()),
        "features": ["step_by_step", "complexity_analysis", "comparison"],
        "price": "free",
        "status": ExpansionStatus.AVAILABLE,
    },
}


__all__ = ["EXPANSION_PACKS"]
