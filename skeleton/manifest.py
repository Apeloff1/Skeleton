"""
Skeleton — Project Manifest and Metadata

Central registry for all modules, their purposes, and interdependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List


# Complete module registry
MODULES: Dict[str, Dict[str, Any]] = {
    # Kernel layer
    "skeleton.kernel.primitives": {
        "layer": "kernel",
        "purpose": "Core types: errors, events, entropy, clocks, invariants, registry",
        "dependencies": [],
        "exports": ["SkeletonError", "BlueprintError", "MaterialisationError", "DomainEvent", "EventBus", "EntropyPool", "VectorClock", "Invariant", "InvariantLattice", "CapabilityRegistry", "UserId", "BlueprintId"],
    },
    "skeleton.kernel.__init__": {
        "layer": "kernel",
        "purpose": "Kernel package exports",
        "dependencies": ["skeleton.kernel.primitives"],
        "exports": ["SkeletonError", "EventBus", "DomainEvent", "UserId", "BlueprintId", "EntropyPool", "VectorClock", "Invariant", "InvariantLattice", "CapabilityRegistry"],
    },
    
    # Configuration layer
    "skeleton.config.system": {
        "layer": "config",
        "purpose": "Layered configuration with defaults, project, user, env, runtime",
        "dependencies": [],
        "exports": ["Config", "get_config", "cfg"],
    },
    "skeleton.config.snapshots": {
        "layer": "config",
        "purpose": "Configuration snapshot save/restore for rollback safety",
        "dependencies": [],
        "exports": ["SettingsSnapshotBridge", "ConfigSnapshot"],
    },
    
    # Memory layer
    "skeleton.memory.core": {
        "layer": "memory",
        "purpose": "RAG, CAG, MAG, Trinity fusion, repetition scheduler",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["InMemoryTFIDFStore", "CAGStore", "MAGStore", "MemoryTrinity", "RepetitionScheduler", "Chunk", "ScoredChunk", "TrinityResult"],
    },
    "skeleton.memory.drift": {
        "layer": "memory",
        "purpose": "Persona behavior drift detection",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["PersonaDriftDetector", "BehaviorSample"],
    },
    "skeleton.memory.guarded_compaction": {
        "layer": "memory",
        "purpose": "Turn history compression with constraint preservation",
        "dependencies": [],
        "exports": ["compact_turns"],
    },
    
    # Intelligence layer
    "skeleton.intelligence.orchestrator": {
        "layer": "intelligence",
        "purpose": "Task coordination and adaptive meta-learning",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["IntelligenceOrchestrator", "AdaptiveLearner", "MetaGrid", "ReasoningTask", "ReasoningResult", "default_meta_grid"],
    },
    
    # Swarm layer
    "skeleton.swarm.mesh": {
        "layer": "swarm",
        "purpose": "Agent routing, pheromones, hive mind, platoons",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["SwarmMesh", "Agent", "PheromoneField", "StigmergicRouter", "HiveMind", "CapabilityNegotiator", "Platoons", "standard_platoons"],
    },
    
    # Forge layer
    "skeleton.forge.universal": {
        "layer": "forge",
        "purpose": "Blueprint composition and materialization",
        "dependencies": ["skeleton.kernel.errors", "skeleton.kernel.events", "skeleton.kernel.ids"],
        "exports": ["Forge", "Blueprint", "Component", "Port", "Wire"],
    },
    
    # Resilience layer
    "skeleton.resilience.core": {
        "layer": "resilience",
        "purpose": "Input sanitization and canary rollouts",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["ResilienceFortress", "CanaryRegistry", "ThreatLevel", "SanitizationReport"],
    },
    
    # Observability layer
    "skeleton.observability.metrics": {
        "layer": "observability",
        "purpose": "Sampling, metrics collection",
        "dependencies": [],
        "exports": ["Sampler", "MetricsCollector", "MetricPoint", "default_sampler"],
    },
    "skeleton.observability.anomaly": {
        "layer": "observability",
        "purpose": "Statistical anomaly detection with adaptive thresholds",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["AnomalyDetector", "AnomalyReport", "AdaptiveThreshold", "SeasonalDecomposer"],
    },
    
    # API layer
    "skeleton.api.server": {
        "layer": "api",
        "purpose": "FastAPI application factory and state management",
        "dependencies": ["skeleton.genesis"],
        "exports": ["create_app", "get_state", "ServerState", "run_server"],
    },
    "skeleton.api.routes": {
        "layer": "api",
        "purpose": "REST API route definitions",
        "dependencies": ["skeleton.api.server", "skeleton.api.hmac_seal"],
        "exports": ["router"],
    },
    "skeleton.api.hmac_seal": {
        "layer": "api",
        "purpose": "HMAC request signing for protected routes",
        "dependencies": [],
        "exports": ["HMACSeal", "require_seal", "get_seal"],
    },
    "skeleton.api.idempotency": {
        "layer": "api",
        "purpose": "Deduplicate retry-sensitive operations",
        "dependencies": [],
        "exports": ["IdempotencyGuard", "IdempotencyEntry"],
    },
    "skeleton.api.oauth": {
        "layer": "api",
        "purpose": "GitHub OAuth integration",
        "dependencies": [],
        "exports": ["client_id", "client_secret", "oauth_card", "authorize_url", "exchange_code"],
    },
    
    # Cortex layer
    "skeleton.cortex.neocortex": {
        "layer": "cortex",
        "purpose": "Observability hub and control surface",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["JeevesCortex", "CortexSnapshot", "ControlSurface"],
    },
    
    # Developer layer
    "skeleton.developer.scaffold": {
        "layer": "developer",
        "purpose": "Project templates and generation",
        "dependencies": [],
        "exports": ["ScaffoldEngine", "list_templates", "TEMPLATES"],
    },
    "skeleton.developer.wizard": {
        "layer": "developer",
        "purpose": "Interactive project builder",
        "dependencies": ["skeleton.developer.scaffold"],
        "exports": ["Wizard", "WizardMode", "SubsystemExplorer"],
    },
    "skeleton.developer.commands": {
        "layer": "developer",
        "purpose": "Command registry and handlers",
        "dependencies": ["skeleton.developer.scaffold", "skeleton.developer.wizard"],
        "exports": ["CommandRegistry", "DevCommandRegistry", "run_dev_command"],
    },
    "skeleton.developer.cli": {
        "layer": "developer",
        "purpose": "Main CLI entry point",
        "dependencies": ["skeleton.developer.commands"],
        "exports": ["run_dev_cli", "show_docs", "dev_help_text"],
    },
    
    # Deploy layer
    "skeleton.deploy.harness": {
        "layer": "deploy",
        "purpose": "Full-stack deployment orchestration",
        "dependencies": ["skeleton.genesis", "skeleton.api.server"],
        "exports": ["Harness"],
    },
    
    # Testing layer
    "skeleton.testing.scaffold": {
        "layer": "testing",
        "purpose": "Test framework with genesis integration",
        "dependencies": ["skeleton.genesis"],
        "exports": ["TestCase", "TestScaffold", "TestOutcome", "TestRunner"],
    },
    
    # Organism layer
    "skeleton.organism.state": {
        "layer": "organism",
        "purpose": "Runtime state, feature flags, health monitoring",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["OrganismState", "FeatureFlags", "HealthMonitor", "QualityState", "append_quality"],
    },
    
    # Pipelines layer
    "skeleton.pipelines.generation": {
        "layer": "pipelines",
        "purpose": "NPC, game logic, animation generation",
        "dependencies": [],
        "exports": ["NPCPipeline", "GameLogicPipeline", "AnimationPipeline", "NPCSpec", "GameLogicSpec", "AnimationSpec"],
    },
    
    # Vault layer
    "skeleton.vault.access": {
        "layer": "vault",
        "purpose": "Access control and envelope encryption",
        "dependencies": [],
        "exports": ["AccessPolicy", "Role", "Permission", "EnvelopeKMS", "ROLE_GUEST", "ROLE_USER", "ROLE_OPERATOR", "ROLE_ADMIN"],
    },
    
    # Retrieval layer
    "skeleton.retrieval.fusion": {
        "layer": "retrieval",
        "purpose": "Multi-plane result fusion",
        "dependencies": [],
        "exports": ["Fuser", "FusionStrategy", "ScoredResult"],
    },
    "skeleton.retrieval.reranker": {
        "layer": "retrieval",
        "purpose": "Feature-based result re-ranking",
        "dependencies": [],
        "exports": ["FeatureReranker", "FeatureExtractor", "RerankScore"],
    },
    "skeleton.retrieval.provenance": {
        "layer": "retrieval",
        "purpose": "Data lineage tracking",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["ProvenanceLedger", "ProvenanceEntry"],
    },
    "skeleton.retrieval.quad": {
        "layer": "retrieval",
        "purpose": "Four-plane unified retrieval",
        "dependencies": ["skeleton.kernel.events", "skeleton.retrieval.fusion"],
        "exports": ["QuadRetriever", "PlaneResult"],
    },
    
    # Agents layer
    "skeleton.agents.coordination": {
        "layer": "agents",
        "purpose": "Agent pool and task coordination",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["Coordinator", "AgentPool", "Task", "TaskStatus"],
    },
    
    # Context layer
    "skeleton.context.questionnaire": {
        "layer": "context",
        "purpose": "Game design intake questionnaire",
        "dependencies": [],
        "exports": ["intake", "Questionnaire", "IntakeResult"],
    },
    
    # Galaxy layer
    "skeleton.galaxy.federation": {
        "layer": "galaxy",
        "purpose": "Distributed node coordination",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["GalaxyNode", "FederationMesh", "NodeRegistry", "NodeIdentity"],
    },
    
    # Social layer
    "skeleton.social.graph": {
        "layer": "social",
        "purpose": "Agent relationships and reputation",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["SocialGraph", "ReputationEngine", "InteractionLog", "Interaction"],
    },
    
    # Integrations layer
    "skeleton.integrations.connectors": {
        "layer": "integrations",
        "purpose": "External service connectors",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["ConnectorRegistry", "WebhookHandler", "APICredentials"],
    },
    
    # Acquired layer
    "skeleton.acquired.ingest": {
        "layer": "acquired",
        "purpose": "Asset ingestion and management",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["AssetLibrary", "AssetIngestor", "AssetValidator", "Asset"],
    },
    
    # Jeeves layer
    "skeleton.jeeves.core": {
        "layer": "jeeves",
        "purpose": "Conversational AI orchestration",
        "dependencies": ["skeleton.kernel.events"],
        "exports": ["JeevesCore", "SessionMode", "Session", "MemoryManager", "Turn"],
    },
    
    # Genesis (orchestrator)
    "skeleton.genesis": {
        "layer": "genesis",
        "purpose": "Boot orchestrator for all 7 phases",
        "dependencies": ["skeleton.kernel.*", "skeleton.memory.*", "skeleton.intelligence.*", "skeleton.swarm.*", "skeleton.resilience.*", "skeleton.observability.*", "skeleton.retrieval.*", "skeleton.cortex.*"],
        "exports": ["Genesis", "GenesisReport"],
    },
    
    # Architecture reference
    "skeleton.architecture": {
        "layer": "meta",
        "purpose": "Architecture documentation and metadata",
        "dependencies": [],
        "exports": ["BOOT_PHASES", "PACKAGES", "API_ROUTES", "CLI_COMMANDS", "TEMPLATES", "get_phase", "get_package", "get_routes", "architecture_summary"],
    },
    
    # Setup configuration
    "skeleton.setup_config": {
        "layer": "meta",
        "purpose": "Package installation metadata",
        "dependencies": [],
        "exports": ["get_setup_config", "PACKAGE_NAME", "VERSION", "CORE_DEPENDENCIES", "OPTIONAL_DEPENDENCIES"],
    },
}


def get_module_info(module_path: str) -> Dict[str, Any]:
    """Get metadata for a specific module."""
    return MODULES.get(module_path, {"error": "Module not found"})


def get_modules_by_layer(layer: str) -> List[str]:
    """Get all module paths for a given layer."""
    return [path for path, info in MODULES.items() if info.get("layer") == layer]


def get_layer_dependencies(layer: str) -> List[str]:
    """Get all layers that a given layer depends on."""
    deps = set()
    for path, info in MODULES.items():
        if info.get("layer") == layer:
            for dep in info.get("dependencies", []):
                dep_layer = dep.split(".")[1] if len(dep.split(".")) > 1 else "unknown"
                deps.add(dep_layer)
    return sorted(deps)


def count_modules() -> Dict[str, int]:
    """Count modules by layer."""
    counts = {}
    for info in MODULES.values():
        layer = info.get("layer", "unknown")
        counts[layer] = counts.get(layer, 0) + 1
    return counts


def manifest_summary() -> Dict[str, Any]:
    """Generate a summary of the complete project manifest."""
    return {
        "total_modules": len(MODULES),
        "by_layer": count_modules(),
        "layers": sorted(set(info.get("layer", "unknown") for info in MODULES.values())),
        "total_exports": sum(len(info.get("exports", [])) for info in MODULES.values()),
    }
