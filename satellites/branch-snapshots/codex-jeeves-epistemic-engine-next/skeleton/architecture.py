"""
Skeleton — Complete Architecture Reference

This module documents the full Skeleton v16 platform architecture.
It is importable for programmatic access to architecture metadata.
"""

from __future__ import annotations

from typing import Any, Dict, List


ARCHITECTURE_VERSION = "16.0.0"
CODENAME = "Skeleton"

# Phase definitions with dependencies and subsystem mappings
BOOT_PHASES: List[Dict[str, Any]] = [
    {
        "phase": "kernel",
        "order": 1,
        "description": "Core primitives and communication fabric",
        "subsystems": [
            {"name": "EventBus", "module": "skeleton.kernel.events", "purpose": "Pub/sub messaging backbone"},
            {"name": "EntropyPool", "module": "skeleton.kernel.entropy", "purpose": "Seeded randomness for reproducibility"},
            {"name": "VectorClock", "module": "skeleton.kernel.clocks", "purpose": "Distributed event ordering"},
            {"name": "InvariantLattice", "module": "skeleton.kernel.invariants", "purpose": "Runtime constraint checking"},
        ],
        "invariants": [],
    },
    {
        "phase": "memory",
        "order": 2,
        "description": "Multi-plane retrieval and storage systems",
        "subsystems": [
            {"name": "InMemoryTFIDFStore", "module": "skeleton.memory.core", "purpose": "Sparse RAG retrieval"},
            {"name": "CAGStore", "module": "skeleton.memory.core", "purpose": "Contextual associative memory"},
            {"name": "MAGStore", "module": "skeleton.memory.core", "purpose": "Multi-agent episodic memory"},
            {"name": "MemoryTrinity", "module": "skeleton.memory.core", "purpose": "Unified RAG+CAG+MAG fusion"},
            {"name": "RepetitionScheduler", "module": "skeleton.memory.core", "purpose": "Spaced repetition consolidation"},
            {"name": "DreamEngine", "module": "skeleton.intelligence.dream", "purpose": "Generative memory synthesis"},
            {"name": "PersonaDriftDetector", "module": "skeleton.memory.drift", "purpose": "Behavior drift detection"},
        ],
        "invariants": [
            {"name": "mag_index_consistent", "description": "MAG indexed episodes ⊆ total episodes"},
        ],
    },
    {
        "phase": "intelligence",
        "order": 3,
        "description": "Reasoning and adaptive learning",
        "subsystems": [
            {"name": "IntelligenceOrchestrator", "module": "skeleton.intelligence.orchestrator", "purpose": "Task coordination across capabilities"},
            {"name": "AdaptiveLearner", "module": "skeleton.intelligence.orchestrator", "purpose": "Meta-learning with hyperparameter grid"},
        ],
        "invariants": [],
    },
    {
        "phase": "swarm",
        "order": 4,
        "description": "Multi-agent coordination and stigmergy",
        "subsystems": [
            {"name": "SwarmMesh", "module": "skeleton.swarm.mesh", "purpose": "Agent routing by capability"},
            {"name": "PheromoneField", "module": "skeleton.swarm.mesh", "purpose": "Stigmergic communication"},
            {"name": "StigmergicRouter", "module": "skeleton.swarm.mesh", "purpose": "Pheromone-influenced routing"},
            {"name": "HiveMind", "module": "skeleton.swarm.mesh", "purpose": "Collective consensus formation"},
            {"name": "CapabilityNegotiator", "module": "skeleton.swarm.mesh", "purpose": "Dynamic capability discovery"},
            {"name": "Platoons", "module": "skeleton.swarm.mesh", "purpose": "Pre-configured agent groups"},
        ],
        "invariants": [
            {"name": "swarm_quorum_viable", "description": "At least one healthy agent in mesh", "severity": "WARNING"},
        ],
    },
    {
        "phase": "resilience",
        "order": 5,
        "description": "Security, fault tolerance, and safe rollouts",
        "subsystems": [
            {"name": "ResilienceFortress", "module": "skeleton.resilience.core", "purpose": "Input sanitization and threat detection"},
            {"name": "CanaryRegistry", "module": "skeleton.resilience.core", "purpose": "Safe rollout monitoring"},
        ],
        "invariants": [],
    },
    {
        "phase": "interface",
        "order": 6,
        "description": "Observability, retrieval, and API surface",
        "subsystems": [
            {"name": "AnomalyDetector", "module": "skeleton.observability.anomaly", "purpose": "Statistical anomaly detection"},
            {"name": "ProvenanceLedger", "module": "skeleton.retrieval.provenance", "purpose": "Data lineage tracking"},
            {"name": "FeatureReranker", "module": "skeleton.retrieval.reranker", "purpose": "Learned result re-ranking"},
            {"name": "QuadRetriever", "module": "skeleton.retrieval.quad", "purpose": "Four-plane unified search"},
        ],
        "invariants": [],
    },
    {
        "phase": "cortex",
        "order": 7,
        "description": "Central observability and control surface",
        "subsystems": [
            {"name": "JeevesCortex", "module": "skeleton.cortex.neocortex", "purpose": "System-wide event observation"},
            {"name": "ControlSurface", "module": "skeleton.cortex.neocortex", "purpose": "Runtime intervention"},
        ],
        "invariants": [],
    },
]

# Package registry with descriptions
PACKAGES: Dict[str, Dict[str, Any]] = {
    "skeleton.kernel": {"description": "Core primitives", "exports": ["EventBus", "EntropyPool", "VectorClock", "InvariantLattice", "SkeletonError"]},
    "skeleton.memory": {"description": "Multi-plane storage", "exports": ["InMemoryTFIDFStore", "CAGStore", "MAGStore", "MemoryTrinity", "RepetitionScheduler"]},
    "skeleton.intelligence": {"description": "Reasoning and learning", "exports": ["IntelligenceOrchestrator", "AdaptiveLearner", "MetaGrid"]},
    "skeleton.swarm": {"description": "Agent coordination", "exports": ["SwarmMesh", "PheromoneField", "HiveMind", "CapabilityNegotiator", "Platoons"]},
    "skeleton.forge": {"description": "Blueprint composition", "exports": ["Forge", "Blueprint", "Component", "Port", "Wire"]},
    "skeleton.resilience": {"description": "Security and fault tolerance", "exports": ["ResilienceFortress", "CanaryRegistry", "ThreatLevel"]},
    "skeleton.observability": {"description": "Metrics and monitoring", "exports": ["Sampler", "MetricsCollector", "AnomalyDetector"]},
    "skeleton.api": {"description": "REST API surface", "exports": ["create_app", "get_state", "ServerState"]},
    "skeleton.cortex": {"description": "Observability hub", "exports": ["JeevesCortex", "CortexSnapshot", "ControlSurface"]},
    "skeleton.developer": {"description": "Developer CLI", "exports": ["ScaffoldEngine", "Wizard", "CommandRegistry"]},
    "skeleton.deploy": {"description": "Deployment harness", "exports": ["Harness", "Config", "get_config"]},
    "skeleton.testing": {"description": "Test framework", "exports": ["TestCase", "TestScaffold", "TestRunner"]},
    "skeleton.organism": {"description": "Runtime state", "exports": ["OrganismState", "FeatureFlags", "HealthMonitor"]},
    "skeleton.pipelines": {"description": "Task pipelines", "exports": ["NPCPipeline", "GameLogicPipeline", "AnimationPipeline"]},
    "skeleton.vault": {"description": "Access control", "exports": ["AccessPolicy", "EnvelopeKMS", "Role"]},
    "skeleton.retrieval": {"description": "Search and fusion", "exports": ["Fuser", "FusionStrategy", "ScoredResult", "Ranker"]},
    "skeleton.agents": {"description": "Agent coordination", "exports": ["Coordinator", "AgentPool", "Task"]},
    "skeleton.context": {"description": "Intake system", "exports": ["intake", "Questionnaire", "IntakeResult"]},
    "skeleton.config": {"description": "Configuration", "exports": ["SettingsSnapshotBridge", "ConfigSnapshot"]},
    "skeleton.galaxy": {"description": "Distributed nodes", "exports": ["GalaxyNode", "FederationMesh", "NodeRegistry"]},
    "skeleton.social": {"description": "Agent interactions", "exports": ["SocialGraph", "ReputationEngine", "InteractionLog"]},
    "skeleton.integrations": {"description": "External connectors", "exports": ["ConnectorRegistry", "WebhookHandler", "APICredentials"]},
    "skeleton.acquired": {"description": "Asset management", "exports": ["AssetLibrary", "AssetIngestor", "AssetValidator"]},
    "skeleton.jeeves": {"description": "Conversational AI", "exports": ["JeevesCore", "SessionMode", "Session", "MemoryManager"]},
}

# API route registry
API_ROUTES: List[Dict[str, Any]] = [
    {"method": "GET", "path": "/api/v1/health", "protected": False, "description": "Health check"},
    {"method": "GET", "path": "/api/v1/health/live", "protected": False, "description": "Liveness probe"},
    {"method": "GET", "path": "/api/v1/health/ready", "protected": False, "description": "Readiness probe"},
    {"method": "GET", "path": "/api/v1/metrics", "protected": False, "description": "Metrics snapshot"},
    {"method": "GET", "path": "/api/v1/genesis", "protected": False, "description": "Boot report"},
    {"method": "GET", "path": "/api/v1/genesis/handles", "protected": False, "description": "Wired handles"},
    {"method": "GET", "path": "/api/v1/capabilities", "protected": False, "description": "Capability registry"},
    {"method": "POST", "path": "/api/v1/retrieval/query", "protected": False, "description": "Multi-plane search"},
    {"method": "POST", "path": "/api/v1/retrieval/ingest", "protected": False, "description": "Document ingestion"},
    {"method": "POST", "path": "/api/v1/retrieval/feedback", "protected": False, "description": "Plane feedback"},
    {"method": "POST", "path": "/api/v1/jeeves/session", "protected": False, "description": "Create session"},
    {"method": "POST", "path": "/api/v1/jeeves/interact", "protected": False, "description": "Send message"},
    {"method": "POST", "path": "/api/v1/jeeves/review", "protected": False, "description": "Code review"},
    {"method": "POST", "path": "/api/v1/jeeves/bind-era", "protected": False, "description": "Bind game era"},
    {"method": "POST", "path": "/api/v1/jeeves/advise", "protected": False, "description": "System advice"},
    {"method": "GET", "path": "/api/v1/jeeves/matrices/{session_id}", "protected": False, "description": "Session matrices"},
    {"method": "POST", "path": "/api/v1/memory/query", "protected": False, "description": "Memory query"},
    {"method": "GET", "path": "/api/v1/swarm/stats", "protected": False, "description": "Swarm statistics"},
    {"method": "POST", "path": "/api/v1/swarm/agent", "protected": False, "description": "Register agent"},
    {"method": "POST", "path": "/api/v1/swarm/route", "protected": False, "description": "Route task"},
    {"method": "GET", "path": "/api/v1/ledger/stats", "protected": False, "description": "Ledger stats"},
    {"method": "GET", "path": "/api/v1/ledger/tail", "protected": False, "description": "Recent ledger entries"},
    {"method": "GET", "path": "/api/v1/scheduler/stats", "protected": False, "description": "Scheduler stats"},
    {"method": "POST", "path": "/api/v1/pipeline/npc", "protected": False, "description": "Generate NPC"},
    {"method": "POST", "path": "/api/v1/pipeline/game-logic", "protected": False, "description": "Design game mechanics"},
    {"method": "POST", "path": "/api/v1/pipeline/animation", "protected": False, "description": "Create animation spec"},
    {"method": "POST", "path": "/api/v1/forge/blueprint", "protected": True, "description": "Create blueprint"},
    {"method": "POST", "path": "/api/v1/forge/materialise", "protected": True, "description": "Materialize blueprint"},
    {"method": "GET", "path": "/api/v1/forge/kinds", "protected": False, "description": "Component kinds"},
    {"method": "GET", "path": "/api/v1/forge/eras", "protected": False, "description": "Available eras"},
    {"method": "POST", "path": "/api/v1/forge/archetype", "protected": True, "description": "Build archetype"},
    {"method": "POST", "path": "/api/v1/intelligence/reason", "protected": False, "description": "Reasoning query"},
    {"method": "POST", "path": "/api/v1/resilience/sanitise", "protected": False, "description": "Input sanitization"},
]

# Developer CLI command registry
CLI_COMMANDS: List[Dict[str, Any]] = [
    {"command": "scaffold", "args": "<name> [--template] [--dir] [--dry-run]", "description": "Generate project from template"},
    {"command": "wizard", "args": "[--answers] [--non-interactive]", "description": "Interactive project builder"},
    {"command": "health", "args": "[--json] [--watch] [--interval]", "description": "Subsystem health dashboard"},
    {"command": "visualize", "args": "[--blueprint] [--topology] [--compact] [--save]", "description": "Blueprint visualization"},
    {"command": "extension", "args": "<name> [--type] [--with-tests] [--with-api]", "description": "Generate subsystem boilerplate"},
    {"command": "list-templates", "args": "", "description": "Show available templates"},
    {"command": "validate", "args": "<path>", "description": "Validate project conventions"},
    {"command": "docs", "args": "[topic]", "description": "Show documentation"},
]

# Template registry
TEMPLATES: List[Dict[str, Any]] = [
    {"name": "minimal-agent", "description": "Lightweight agent core", "files": ["agent.py", "main.py", "README.md"]},
    {"name": "game-forge", "description": "Game development scaffold", "files": ["game.py", "main.py", "README.md"]},
    {"name": "swarm-orchestrator", "description": "Multi-agent orchestration", "files": ["swarm.py", "main.py", "README.md"]},
    {"name": "api-gateway", "description": "REST API service template", "files": ["service.py", "main.py", "README.md"]},
]


def get_phase(phase_name: str) -> Optional[Dict[str, Any]]:
    """Get phase definition by name."""
    for phase in BOOT_PHASES:
        if phase["phase"] == phase_name:
            return phase
    return None


def get_package(package_name: str) -> Optional[Dict[str, Any]]:
    """Get package definition by name."""
    return PACKAGES.get(package_name)


def get_routes(protected_only: bool = False) -> List[Dict[str, Any]]:
    """Get API routes, optionally filtering to protected only."""
    if protected_only:
        return [r for r in API_ROUTES if r.get("protected")]
    return API_ROUTES


def architecture_summary() -> Dict[str, Any]:
    """Generate a summary of the full architecture."""
    return {
        "version": ARCHITECTURE_VERSION,
        "codename": CODENAME,
        "phases": len(BOOT_PHASES),
        "packages": len(PACKAGES),
        "api_routes": len(API_ROUTES),
        "cli_commands": len(CLI_COMMANDS),
        "templates": len(TEMPLATES),
        "subsystems": sum(len(p["subsystems"]) for p in BOOT_PHASES),
        "invariants": sum(len(p.get("invariants", [])) for p in BOOT_PHASES),
    }
