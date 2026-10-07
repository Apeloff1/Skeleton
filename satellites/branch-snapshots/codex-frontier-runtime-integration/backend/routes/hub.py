"""
Ultimate Hub Routes - Language Packs, Expansions, Algorithms
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Hub"])

# Language Packs by Category
LANGUAGE_PACKS = {
    "systems": [
        {"id": "rust", "name": "Rust", "version": "1.75", "icon": "🦀"},
        {"id": "go", "name": "Go", "version": "1.22", "icon": "🐹"},
        {"id": "zig", "name": "Zig", "version": "0.12", "icon": "⚡"},
        {"id": "nim", "name": "Nim", "version": "2.0", "icon": "👑"},
        {"id": "crystal", "name": "Crystal", "version": "1.11", "icon": "💎"},
        {"id": "d", "name": "D", "version": "2.107", "icon": "🔷"},
        {"id": "v", "name": "V", "version": "0.4", "icon": "✌️"},
        {"id": "odin", "name": "Odin", "version": "dev", "icon": "🔱"}
    ],
    "functional": [
        {"id": "haskell", "name": "Haskell", "version": "9.8", "icon": "λ"},
        {"id": "ocaml", "name": "OCaml", "version": "5.1", "icon": "🐫"},
        {"id": "fsharp", "name": "F#", "version": "8.0", "icon": "#️⃣"},
        {"id": "elixir", "name": "Elixir", "version": "1.16", "icon": "💧"},
        {"id": "erlang", "name": "Erlang", "version": "26", "icon": "📞"},
        {"id": "clojure", "name": "Clojure", "version": "1.11", "icon": "🔄"},
        {"id": "scheme", "name": "Scheme", "version": "R7RS", "icon": "🎭"},
        {"id": "racket", "name": "Racket", "version": "8.12", "icon": "🎾"}
    ],
    "scientific": [
        {"id": "julia", "name": "Julia", "version": "1.10", "icon": "📊"},
        {"id": "r", "name": "R", "version": "4.3", "icon": "📈"},
        {"id": "octave", "name": "GNU Octave", "version": "9.1", "icon": "🔢"},
        {"id": "fortran", "name": "Fortran", "version": "2023", "icon": "🏛️"},
        {"id": "wolfram", "name": "Wolfram", "version": "14", "icon": "🔴"}
    ],
    "mobile": [
        {"id": "swift", "name": "Swift", "version": "5.10", "icon": "🍎"},
        {"id": "kotlin", "name": "Kotlin", "version": "2.0", "icon": "🤖"},
        {"id": "dart", "name": "Dart", "version": "3.3", "icon": "🎯"},
        {"id": "objc", "name": "Objective-C", "version": "2.0", "icon": "📱"}
    ],
    "blockchain": [
        {"id": "solidity", "name": "Solidity", "version": "0.8", "icon": "⟠"},
        {"id": "vyper", "name": "Vyper", "version": "0.4", "icon": "🐍"},
        {"id": "move", "name": "Move", "version": "1.0", "icon": "🔷"}
    ],
    "proof": [
        {"id": "coq", "name": "Coq", "version": "8.18", "icon": "🐓"},
        {"id": "lean", "name": "Lean 4", "version": "4.4", "icon": "📐"},
        {"id": "idris", "name": "Idris 2", "version": "0.7", "icon": "🔮"},
        {"id": "agda", "name": "Agda", "version": "2.6", "icon": "∀"}
    ],
    "hardware": [
        {"id": "verilog", "name": "Verilog", "version": "2005", "icon": "🔌"},
        {"id": "vhdl", "name": "VHDL", "version": "2019", "icon": "⚡"},
        {"id": "chisel", "name": "Chisel", "version": "6.0", "icon": "🛠️"},
        {"id": "spinalhdl", "name": "SpinalHDL", "version": "1.10", "icon": "🌀"}
    ],
    "assembly": [
        {"id": "x86", "name": "x86 Assembly", "version": "64-bit", "icon": "🖥️"},
        {"id": "arm", "name": "ARM Assembly", "version": "v9", "icon": "💪"},
        {"id": "wasm", "name": "WebAssembly", "version": "2.0", "icon": "🌐"},
        {"id": "llvm_ir", "name": "LLVM IR", "version": "18", "icon": "🐉"}
    ]
}

# Expansion Packs
EXPANSION_PACKS = [
    {"id": "systems_pro", "name": "Systems Programming Pro", "languages": 8, "price": "free"},
    {"id": "data_science", "name": "Data Science Suite", "languages": 5, "price": "free"},
    {"id": "mobile_dev", "name": "Mobile Development Kit", "languages": 4, "price": "free"},
    {"id": "functional", "name": "Functional Programming Mastery", "languages": 8, "price": "free"},
    {"id": "blockchain", "name": "Blockchain Development", "languages": 3, "price": "free"},
    {"id": "theorem_provers", "name": "Theorem Provers & Formal Methods", "languages": 4, "price": "free"},
    {"id": "compiler_internals", "name": "Compiler Internals Deep Dive", "tools": 10, "price": "free"},
    {"id": "hardware_design", "name": "Hardware Design Suite", "languages": 4, "price": "free"},
    {"id": "ai_ml_toolkit", "name": "AI/ML Integration Toolkit", "models": 5, "price": "free"},
    {"id": "algorithm_explorer", "name": "Algorithm Explorer Pro", "algorithms": 35, "price": "free"}
]

# Algorithm Registry
ALGORITHM_REGISTRY = {
    "parsing": [
        {"id": "ll1", "name": "LL(1) Parser", "complexity": "O(n)"},
        {"id": "lr1", "name": "LR(1) Parser", "complexity": "O(n)"},
        {"id": "lalr", "name": "LALR(1) Parser", "complexity": "O(n)"},
        {"id": "glr", "name": "GLR Parser", "complexity": "O(n³)"},
        {"id": "earley", "name": "Earley Parser", "complexity": "O(n³)"},
        {"id": "peg", "name": "PEG Parser", "complexity": "O(n)"},
        {"id": "pratt", "name": "Pratt Parser", "complexity": "O(n)"}
    ],
    "optimization": [
        {"id": "ssa", "name": "SSA Construction", "type": "IR"},
        {"id": "gcse", "name": "Global CSE", "type": "optimization"},
        {"id": "licm", "name": "Loop Invariant Code Motion", "type": "optimization"},
        {"id": "strength_reduction", "name": "Strength Reduction", "type": "optimization"},
        {"id": "vectorization", "name": "Vectorization", "type": "optimization"},
        {"id": "polyhedral", "name": "Polyhedral Optimization", "type": "advanced"}
    ],
    "register_allocation": [
        {"id": "linear_scan", "name": "Linear Scan", "complexity": "O(n)"},
        {"id": "graph_coloring", "name": "Graph Coloring", "complexity": "O(n²)"},
        {"id": "chaitin_briggs", "name": "Chaitin-Briggs", "complexity": "O(n²)"},
        {"id": "pbqp", "name": "PBQP", "complexity": "O(n³)"}
    ],
    "garbage_collection": [
        {"id": "mark_sweep", "name": "Mark-Sweep", "type": "tracing"},
        {"id": "mark_compact", "name": "Mark-Compact", "type": "tracing"},
        {"id": "copying", "name": "Copying GC", "type": "tracing"},
        {"id": "generational", "name": "Generational GC", "type": "tracing"},
        {"id": "concurrent", "name": "Concurrent GC", "type": "advanced"},
        {"id": "ref_counting", "name": "Reference Counting", "type": "counting"}
    ]
}


@router.get("/v9/info")
async def get_hub_info():
    """Get Ultimate Hub information"""
    total_languages = sum(len(packs) for packs in LANGUAGE_PACKS.values())
    total_algorithms = sum(len(algs) for algs in ALGORITHM_REGISTRY.values())
    
    return {
        "name": "CodeDock Ultimate Hub",
        "version": "9.0.0",
        "language_packs": total_languages,
        "expansion_packs": len(EXPANSION_PACKS),
        "algorithms": total_algorithms,
        "categories": list(LANGUAGE_PACKS.keys())
    }


@router.get("/language-packs")
async def get_language_packs():
    """Get all language packs by category"""
    return {
        "categories": LANGUAGE_PACKS,
        "total": sum(len(packs) for packs in LANGUAGE_PACKS.values())
    }


@router.get("/language-packs/{category}")
async def get_language_pack_by_category(category: str):
    """Get language packs for a specific category"""
    if category not in LANGUAGE_PACKS:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"category": category, "languages": LANGUAGE_PACKS[category]}


@router.get("/expansions")
async def get_expansions():
    """Get all expansion packs"""
    return {"expansions": EXPANSION_PACKS, "total": len(EXPANSION_PACKS)}


@router.get("/expansions/{pack_id}")
async def get_expansion(pack_id: str):
    """Get specific expansion pack"""
    for pack in EXPANSION_PACKS:
        if pack["id"] == pack_id:
            return pack
    raise HTTPException(status_code=404, detail="Expansion pack not found")


@router.post("/expansions/{pack_id}/install")
async def install_expansion(pack_id: str):
    """Install an expansion pack"""
    for pack in EXPANSION_PACKS:
        if pack["id"] == pack_id:
            return {"status": "installed", "pack": pack}
    raise HTTPException(status_code=404, detail="Expansion pack not found")


@router.get("/algorithms")
async def get_algorithms():
    """Get all algorithms by category"""
    return {
        "categories": ALGORITHM_REGISTRY,
        "total": sum(len(algs) for algs in ALGORITHM_REGISTRY.values())
    }


@router.get("/algorithms/{category}")
async def get_algorithms_by_category(category: str):
    """Get algorithms for a specific category"""
    if category not in ALGORITHM_REGISTRY:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"category": category, "algorithms": ALGORITHM_REGISTRY[category]}
