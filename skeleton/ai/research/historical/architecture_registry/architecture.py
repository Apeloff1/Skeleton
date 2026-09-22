"""
Skeleton — Complete Architecture Reference

This module documents the full Skeleton v16 platform architecture.
It is importable for programmatic access to architecture metadata.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


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
    "skeleton.application": {"description": "Shared command contracts", "exports": [
        "ALLOW_LIST_AUDIT_KIND", "ADMIT_WRITE_AUDIT_KIND", "API_ROUTE_AUDIT_KIND", "APP_ROUTE_AUDIT_KIND",
        "AUDITED_PLANE_IDS", "AUTHZ_AUDIT_KIND", "CAPABILITIES",
        "CAPABILITIES_BY_ID", "CAPABILITY_LOADER", "CAPABILITY_MANIFEST_VERSION", "CAPABILITY_VIEW_AUDIT_KIND",
        "CHARTER_AUDIT_KIND", "CLI_SHARED_AUDIT_KIND", "CODENAME_AUDIT_KIND", "CONTRACT_AUDIT_KIND", "CONTRACT_VERSION",
        "CONTRACT_VERSION_AUDIT_KIND",
        "CORTEX_ROUTE_AUDIT_KIND", "DEVELOPER_CLI_AUDIT_KIND", "DEV_TOKEN_AUDIT_KIND",
        "ENV_FLAG_AUDIT_KIND", "EXPORT_AUDIT_KIND", "GATE_DOMAIN_AUDIT_KIND", "GATE_LIMIT_AUDIT_KIND",
        "GATE_STACK_AUDIT_KIND", "GENESIS_BOOT_AUDIT_KIND",
        "HMAC_OPEN_AUDIT_KIND", "IDEMPOTENCY_AUDIT_KIND", "LIVE_HMAC_AUDIT_KIND", "MAIN_CLI_AUDIT_KIND",
        "MOUNTED_ROUTE_AUDIT_KIND",
        "NESTED_ROUTER_AUDIT_KIND", "OPEN_DEV_AUDIT_KIND", "PLANE_AUDIT_KIND", "SEAL_AUDIT_KIND",
        "SESSION_MODE_AUDIT_KIND",
        "SIDECAR_ROUTE_AUDIT_KIND",
        "TEMPLATE_AUDIT_KIND", "TTL_AUDIT_KIND", "VERSION_AUDIT_KIND",
        "Capability", "CapabilityLoadError", "CapabilityLoader", "CapabilityRuntimeStatus",
        "CommandError", "CommandResult", "CommandService", "CommandSpec", "admit_write_audit_snapshot",
        "allow_list_audit_snapshot", "api_route_audit_snapshot",
        "app_route_audit_snapshot", "authz_audit_snapshot", "build_runtime_command_service",
        "capability_lifecycle_snapshot",
        "capability_manifest", "capability_runtime_status", "capability_view_audit_snapshot",
        "charter_audit_snapshot", "cli_shared_audit_snapshot", "codename_audit_snapshot", "command_specs",
        "contract_audit_snapshot", "contract_version_audit_snapshot", "cortex_route_audit_snapshot", "developer_cli_audit_snapshot",
        "dev_token_audit_snapshot",
        "env_flag_audit_snapshot", "export_audit_snapshot", "gate_domain_audit_snapshot",
        "gate_limit_audit_snapshot", "gate_stack_audit_snapshot",
        "genesis_boot_audit_snapshot", "get_admit_write_audit_row", "get_allow_list_audit_row",
        "get_api_route_audit_row",
        "get_app_route_audit_row", "get_authz_audit_row",
        "get_capability", "get_capability_view_audit_row", "get_charter_audit_row",
        "get_cli_shared_audit_row", "get_codename_audit_row", "get_contract_audit_row",
        "get_contract_version_audit_row",
        "get_cortex_route_audit_row",
        "get_developer_cli_audit_row", "get_dev_token_audit_row", "get_env_flag_audit_row",
        "get_export_audit_row",
        "get_gate_domain_audit_row", "get_gate_limit_audit_row", "get_gate_stack_audit_row",
        "get_genesis_boot_audit_row",
        "get_hmac_open_audit_row",
        "get_idempotency_audit_row", "get_live_hmac_audit_row", "get_main_cli_audit_row",
        "get_mounted_route_audit_row",
        "get_nested_router_audit_row", "get_open_dev_audit_row", "get_plane_audit_row",
        "get_seal_audit_row",
        "get_session_mode_audit_row",
        "get_sidecar_route_audit_row",
        "get_template_audit_row", "get_ttl_audit_row", "get_version_audit_row", "hmac_open_audit_snapshot",
        "idempotency_audit_snapshot",
        "live_hmac_audit_snapshot",
        "load_capability", "main_cli_audit_snapshot", "mounted_route_audit_snapshot",
        "nested_router_audit_snapshot", "open_dev_audit_snapshot", "parity_matrix",
        "plane_audit_snapshot",
        "seal_audit_snapshot",
        "session_mode_audit_snapshot",
        "sidecar_route_audit_snapshot", "template_audit_snapshot", "ttl_audit_snapshot", "version_audit_snapshot",
    ]},
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
    "skeleton.organism": {"description": "Runtime state", "exports": ["OrganismState", "FeatureFlags", "HealthMonitor", "QualityState", "append_quality"]},
    "skeleton.pipelines": {"description": "Task pipelines", "exports": ["NPCPipeline", "GameLogicPipeline", "AnimationPipeline"]},
    "skeleton.vault": {"description": "Access control", "exports": ["AccessPolicy", "EnvelopeKMS", "Role"]},
    "skeleton.retrieval": {"description": "Search and fusion", "exports": ["Fuser", "FusionStrategy", "ScoredResult", "Ranker"]},
    "skeleton.agents": {"description": "Agent coordination", "exports": ["Coordinator", "AgentPool", "Task"]},
    "skeleton.context": {"description": "Intake system", "exports": ["intake", "Questionnaire", "IntakeResult"]},
    "skeleton.config": {"description": "Configuration", "exports": ["SettingsSnapshotBridge", "ConfigSnapshot"]},
    "skeleton.content": {"description": "Domain knowledge packs", "exports": ["LOREBUFFA_AI_PACK", "get_npc_context"]},
    "skeleton.galaxy": {"description": "Distributed nodes", "exports": ["GalaxyNode", "FederationMesh", "NodeRegistry", "NodeIdentity", "NodeTransport", "ConsensusEngine", "Proposal", "KAGSync", "GalaxyBridge", "RemoteTask", "LeaderElection", "LeadershipState", "FleetCoordinator", "LoadLedger"]},
    "skeleton.social": {"description": "Agent interactions", "exports": ["SocialGraph", "ReputationEngine", "InteractionLog", "Interaction"]},
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
    {"method": "GET", "path": "/api/v1/application/capabilities", "protected": False, "description": "Curated capability manifest"},
    {"method": "GET", "path": "/api/v1/application/capabilities/lifecycle", "protected": False, "description": "Capability lifecycle snapshot"},
    {"method": "GET", "path": "/api/v1/application/capabilities/{capability_id}", "protected": False, "description": "One curated capability"},
    {"method": "GET", "path": "/api/v1/application/capabilities/export-audit", "protected": False, "description": "Manifest export-drift audit"},
    {"method": "GET", "path": "/api/v1/application/capabilities/export-audit/{capability_id}", "protected": False, "description": "One capability export-audit row"},
    {"method": "GET", "path": "/api/v1/application/planes/audit", "protected": False, "description": "Organism/social/galaxy plane audit"},
    {"method": "GET", "path": "/api/v1/application/planes/audit/{plane_id}", "protected": False, "description": "One audited plane row"},
    {"method": "GET", "path": "/api/v1/application/genesis/audit", "protected": False, "description": "Genesis versus BOOT_PHASES audit"},
    {"method": "GET", "path": "/api/v1/application/genesis/audit/{phase_id}", "protected": False, "description": "One genesis boot-audit row"},
    {"method": "GET", "path": "/api/v1/application/routes/audit", "protected": False, "description": "Main-router API_ROUTES audit"},
    {"method": "GET", "path": "/api/v1/application/routes/audit/{method}/{path}", "protected": False, "description": "One main-router audit row"},
    {"method": "GET", "path": "/api/v1/application/hmac/audit", "protected": False, "description": "HMAC open-prefix versus API_ROUTES audit"},
    {"method": "GET", "path": "/api/v1/application/hmac/audit/{method}/{path}", "protected": False, "description": "One HMAC open-audit row"},
    {"method": "GET", "path": "/api/v1/application/cli/audit", "protected": False, "description": "Developer CLI versus CLI_COMMANDS audit"},
    {"method": "GET", "path": "/api/v1/application/cli/audit/{command_id}", "protected": False, "description": "One developer-CLI audit row"},
    {"method": "GET", "path": "/api/v1/application/templates/audit", "protected": False, "description": "Scaffold TEMPLATES versus architecture audit"},
    {"method": "GET", "path": "/api/v1/application/templates/audit/{template_id}", "protected": False, "description": "One scaffold-template audit row"},
    {"method": "GET", "path": "/api/v1/application/sidecars/audit", "protected": False, "description": "GameForge/command sidecar router audit"},
    {"method": "GET", "path": "/api/v1/application/sidecars/audit/{method}/{path}", "protected": False, "description": "One sidecar-router audit row"},
    {"method": "GET", "path": "/api/v1/application/domains/audit", "protected": False, "description": "Gate-domain versus API_ROUTES audit"},
    {"method": "GET", "path": "/api/v1/application/domains/audit/{path}", "protected": False, "description": "One gate-domain audit row"},
    {"method": "GET", "path": "/api/v1/application/cortex/audit", "protected": False, "description": "Unmounted cortex register_routes audit"},
    {"method": "GET", "path": "/api/v1/application/cortex/audit/{method}/{path}", "protected": False, "description": "One unmounted cortex-route audit row"},
    {"method": "GET", "path": "/api/v1/application/mounted/audit", "protected": False, "description": "create_app-mounted swarm/cockpit router audit"},
    {"method": "GET", "path": "/api/v1/application/mounted/audit/{method}/{path}", "protected": False, "description": "One mounted sidecar-router audit row"},
    {"method": "GET", "path": "/api/v1/application/main-cli/audit", "protected": False, "description": "Main CLI help versus dispatch audit"},
    {"method": "GET", "path": "/api/v1/application/main-cli/audit/{command_id}", "protected": False, "description": "One main-CLI audit row"},
    {"method": "GET", "path": "/api/v1/application/app/audit", "protected": False, "description": "create_app inline handler audit"},
    {"method": "GET", "path": "/api/v1/application/app/audit/{method}/{path}", "protected": False, "description": "One create_app inline-handler audit row"},
    {"method": "GET", "path": "/api/v1/application/charter/audit", "protected": False, "description": "require_charter domain/action audit"},
    {"method": "GET", "path": "/api/v1/application/charter/audit/{method}/{path}", "protected": False, "description": "One charter-binding audit row"},
    {"method": "GET", "path": "/api/v1/application/contracts/audit", "protected": False, "description": "Command contract versus runtime-register audit"},
    {"method": "GET", "path": "/api/v1/application/contracts/audit/{command_id}", "protected": False, "description": "One command-contract audit row"},
    {"method": "GET", "path": "/api/v1/application/hmac/live-audit", "protected": False, "description": "HMAC open-prefix versus live handler union"},
    {"method": "GET", "path": "/api/v1/application/hmac/live-audit/{method}/{path}", "protected": False, "description": "One live-HMAC audit row"},
    {"method": "GET", "path": "/api/v1/application/nested/audit", "protected": False, "description": "Nested include_router audit"},
    {"method": "GET", "path": "/api/v1/application/nested/audit/{include_id}", "protected": False, "description": "One nested-include audit row"},
    {"method": "GET", "path": "/api/v1/application/env/audit", "protected": False, "description": "Process environment-flag audit"},
    {"method": "GET", "path": "/api/v1/application/env/audit/{flag_id}", "protected": False, "description": "One environment-flag audit row"},
    {"method": "GET", "path": "/api/v1/application/views/audit", "protected": False, "description": "Capability-view flag inventory audit"},
    {"method": "GET", "path": "/api/v1/application/views/audit/{flag_id}", "protected": False, "description": "One capability-view flag audit row"},
    {"method": "GET", "path": "/api/v1/application/idempotency/audit", "protected": False, "description": "IdempotencyGuard handler audit"},
    {"method": "GET", "path": "/api/v1/application/idempotency/audit/{handler_id}", "protected": False, "description": "One idempotency-handler audit row"},
    {"method": "GET", "path": "/api/v1/application/seal/audit", "protected": False, "description": "Live require_seal versus HMAC open audit"},
    {"method": "GET", "path": "/api/v1/application/seal/audit/{method}/{path}", "protected": False, "description": "One live-seal audit row"},
    {"method": "GET", "path": "/api/v1/application/admit/audit", "protected": False, "description": "WriteAdmit mutating-method audit"},
    {"method": "GET", "path": "/api/v1/application/admit/audit/{method_id}", "protected": False, "description": "One write-admit method audit row"},
    {"method": "GET", "path": "/api/v1/application/limits/audit", "protected": False, "description": "Gate body/header limit environment audit"},
    {"method": "GET", "path": "/api/v1/application/limits/audit/{flag_id}", "protected": False, "description": "One gate-limit environment audit row"},
    {"method": "GET", "path": "/api/v1/application/shared/audit", "protected": False, "description": "Main-CLI shared-command mapping audit"},
    {"method": "GET", "path": "/api/v1/application/shared/audit/{command_id}", "protected": False, "description": "One shared-command mapping audit row"},
    {"method": "GET", "path": "/api/v1/application/stack/audit", "protected": False, "description": "install_gate middleware-order audit"},
    {"method": "GET", "path": "/api/v1/application/stack/audit/{layer_id}", "protected": False, "description": "One gate-stack middleware audit row"},
    {"method": "GET", "path": "/api/v1/application/allow/audit", "protected": False, "description": "MATERIALISE_TARGETS / curve allow-list audit"},
    {"method": "GET", "path": "/api/v1/application/allow/audit/{handler_id}", "protected": False, "description": "One allow-list usage audit row"},
    {"method": "GET", "path": "/api/v1/application/version/audit", "protected": False, "description": "Advertised version-identity audit"},
    {"method": "GET", "path": "/api/v1/application/version/audit/{source_id}", "protected": False, "description": "One version-identity audit row"},
    {"method": "GET", "path": "/api/v1/application/authz/audit", "protected": False, "description": "CommandSpec mutating vs auth_required audit"},
    {"method": "GET", "path": "/api/v1/application/authz/audit/{command_id}", "protected": False, "description": "One authz-audit command row"},
    {"method": "GET", "path": "/api/v1/application/open-dev/audit", "protected": False, "description": "Opt-in public-dev HMAC prefix audit"},
    {"method": "GET", "path": "/api/v1/application/open-dev/audit/{prefix_id}", "protected": False, "description": "One public-dev prefix audit row"},
    {"method": "GET", "path": "/api/v1/application/tokens/audit", "protected": False, "description": "Public-dev surface token audit"},
    {"method": "GET", "path": "/api/v1/application/tokens/audit/{token_id}", "protected": False, "description": "One public-dev token audit row"},
    {"method": "GET", "path": "/api/v1/application/mode/audit", "protected": False, "description": "SessionMode core vs llm_core identity audit"},
    {"method": "GET", "path": "/api/v1/application/mode/audit/{source_id}", "protected": False, "description": "One SessionMode identity audit row"},
    {"method": "GET", "path": "/api/v1/application/codename/audit", "protected": False, "description": "Advertised codename-identity audit"},
    {"method": "GET", "path": "/api/v1/application/codename/audit/{source_id}", "protected": False, "description": "One codename-identity audit row"},
    {"method": "GET", "path": "/api/v1/application/cver/audit", "protected": False, "description": "Command contract-version identity audit"},
    {"method": "GET", "path": "/api/v1/application/cver/audit/{source_id}", "protected": False, "description": "One contract-version identity audit row"},
    {"method": "GET", "path": "/api/v1/application/ttl/audit", "protected": False, "description": "HMAC and idempotency TTL identity audit"},
    {"method": "GET", "path": "/api/v1/application/ttl/audit/{source_id}", "protected": False, "description": "One TTL-identity audit row"},
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
    {"method": "GET", "path": "/api/v1/resilience/stats", "protected": False, "description": "Resilience statistics"},
    {"method": "GET", "path": "/api/v1/interface/reranker/stats", "protected": False, "description": "Reranker statistics"},
    {"method": "GET", "path": "/api/v1/context/snapshot", "protected": False, "description": "Cockpit snapshot"},
    {"method": "POST", "path": "/api/v1/context/command", "protected": False, "description": "Apply cockpit command"},
    {"method": "POST", "path": "/api/v1/gameforge/run", "protected": True, "description": "Run GameForge generation"},
    {"method": "POST", "path": "/api/v1/gameforge/intake", "protected": True, "description": "GameForge intake questionnaire"},
    {"method": "POST", "path": "/api/v1/swarm/submit", "protected": True, "description": "Submit swarm task"},
    {"method": "GET", "path": "/api/v1/auth/github", "protected": False, "description": "GitHub auth status"},
    {"method": "GET", "path": "/api/v1/auth/github/start", "protected": False, "description": "Start GitHub OAuth"},
    {"method": "GET", "path": "/api/v1/auth/github/callback", "protected": False, "description": "GitHub OAuth callback"},
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
