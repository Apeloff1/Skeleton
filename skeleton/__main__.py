"""Skeleton CLI entry point.

Usage:
    python -m skeleton <command> [options]

Commands:
    app         Unified application assembly (status/check/up/down/ps/logs/smoke)
    ready       Organism readiness, optional --fix/--walk and bounded -n
    product     Live operator product and policy card
    health      Live organism health card (nonzero when degraded)
    next        Next recommended organism action
    wiki         Bounded read-only Hoag/wiki atom-query handles
    seed         Existing organism/kernel owner
    caps         Existing organism/kernel owner
    lattice      Existing organism/kernel owner
    pulse        Existing organism/kernel owner
    orch         Existing organism/kernel owner
    season       Existing organism/kernel owner
    scoreboard   Existing organism/kernel owner
    hot          Existing organism/kernel owner
    coverage     Existing organism/kernel owner
    decade       Existing organism/kernel owner
    bank         Existing organism/kernel owner
    switch       Existing organism/kernel owner
    witness      Existing organism/kernel owner
    gov          Existing organism/kernel owner
    cage         Existing organism/kernel owner
    rot          Existing organism/kernel owner
    fieldcov     Existing organism/kernel owner
    enact        Existing organism/kernel owner
    day          Existing organism/kernel owner
    week         Existing organism/kernel owner
    calendar     Existing organism/kernel owner
    conductor    Existing organism/kernel owner
    ctx          Existing organism/kernel owner
    live         Existing organism/kernel owner
    observe      Existing organism/kernel owner
    stacks       Existing organism/kernel owner
    mix          Existing organism/kernel owner
    satellites   Existing organism/kernel owner
    path         Existing organism/kernel owner
    bound        Existing organism/kernel owner
    fieldwalk    Existing organism/kernel owner
    dump         Existing organism/kernel owner
    orgwalk      Existing organism/kernel owner
    sleep        Existing organism/kernel owner
    forget       Existing organism/kernel owner
    helix        Existing organism/kernel owner
    recall       Existing organism/kernel owner
    run         Start the skeleton runtime / GameForge vision run
                run <vision> [--answers JSON|FILE|@FILE] [--answers-file FILE]
                    [--era ID] [--archetype NAME] [--out DIR] [--overwrite]
                    [--playtest off|auto|require] [--repair-mode apply|suggest]
                    [--blend ERA1 ERA2 --t 0..1] [--generation ID] [--json]
    scene-author  Atomically edit playable scene worlds and preview routes
    scene-circuit  Play switch puzzles and conditional gates
    scene-circuit-solve  Solve replayable circuit routes with bounded search
    scene-circuit-author  Atomically edit and preview playable circuit sources
    scene-circuit-accept  End-to-end acceptance for authored, playable circuit puzzles
    scene-patrol-solve  Find bounded legal routes through timed guards
    scene-patrol-author  Transactionally edit and preview timed patrols
    scene-patrol  Play timed guard routes and replay-verified scene checkpoints
    scene-accept  Audit playable scenes, verify replay and portable exports
    scene-travel  Simulate, verify and resume original offline scene journeys
    scene-survival-campaign  Play replay-verified multi-stage survival campaigns
    scene-survival-campaign-author  Edit and preview multi-stage survival campaigns
    scene-survival-campaign-route  Solve and verify campaign stage routes
    scene-survival-campaign-play  Play campaigns with restartable checkpoints
    scene-survival-campaign-accept  Verify end-to-end playable campaign delivery
    scene-survival-play  Interactively play survival with restartable checkpoints
    scene-survival-author  Transactionally edit survival sources and preview play
    scene-survival-route  Find replay-proven bounded survival routes
    scene-survival  Play source-bound tile hazards, earned food, shelter and replay
    scene-weather  Deterministic authored weather and earned protection over playable survival
    scene-weather-author  Transactional weather source editing and replay-safe previews
    scene-weather-play  Stream-based weather gameplay with verified restartable checkpoints
    scene-weather-board  Source-bound read-only weather board: legal moves, resources and forecast
    scene-weather-route  Bounded canonical weather routing; never assert impossibility from exhaustion
    scene-weather-accept  Playable weather delivery acceptance: source -> CLI -> replay -> export
    scene-market-fork-play  Interactive player selection of replay-proven offline market futures
    scene-market-fork-author  Transactional creator editing for replay-proven market choice forks
    scene-market-fork-accept  End-to-end delivery certification for an authored, won market fork
    scene-market-fork  Replay-proven alternative futures for a player-authored scene market
    scene-market-hours  Deterministic merchant opening hours over canonical earned-currency market pla
    scene-market-hours-play  Bounded interactive merchant-hour gameplay with restartable verified saves
    scene-market-hours-accept  Exact-source merchant gameplay acceptance: replay, economy, board and export
    scene-market-contract-play  JSON-line interactive market contracts with durable canonical checkpoints
    scene-market-contract-accept  End-to-end market commission acceptance across source, play, replay and export
    scene-market-contract  Authored timed delivery contracts on the canonical, replay-verified scene mark
    scene-market-contract-author  Transactional, source-digest-fenced editing for authored market commissions
    scene-market-contract-route  Bounded contract campaign route discovery with canonical replay witnesses
    scene-market-route-accept  End-to-end acceptance of a replay-proven offline market route
    scene-market-route  Bounded, replay-proven market route search over the canonical tile/economy red
    scene-market-board  Player-facing market order board and deterministic non-mutating hints
    scene-market-accept  Verify game-to-export market acceptance evidence
    scene-market-play  Play offline market quests with durable checkpoints
    scene-market-author  Edit and preview source-bound trading quests
    scene-evacuation  Deterministic, source-bound multi-person evacuation over the mission director
    scene-evacuation-board  Legal, replay-proven evacuation choices for CLI, UI and automated play
    scene-evacuation-author  Transactional, digest-fenced editing of authored evacuation NPC contracts
    scene-evacuation-accept  End-to-end source, player decisions, restart, replay and export acceptance
    scene-evacuation-solve  Bounded, fail-closed evacuation route search with canonical replay witnesses
    scene-evacuation-play  Player-facing evacuation turns with legal action previews and checkpoints
    scene-market-party  Cooperative source-bound market campaign with role-gated turns and replay
    scene-market-party-author  Source-digest-fenced cooperative market role editor with replayable receipts
    scene-market-party-play  Interactive cooperative market with bounded retries and verified checkpoints
    scene-market-party-board  Read-only, replay-proven legal turn board for cooperative market players
    scene-market-party-route  Replay-proven cooperative market route search with strict turn arbitration
    scene-market-party-accept  End-to-end acceptance of cooperative player turns and portable market saves
    scene-market-party-timeline  Bounded, replay-proven cooperative market timeline and branch editor
    scene-market-party-league  Replay-scored cooperative market league with no synthetic rewards
    scene-market-party-league-author  Transactional offline authoring and playable previews for market leagues
    scene-market-party-compare  Deterministic cooperative playthrough comparison and safe branch selection
    scene-market-party-portfolio  Portable source-bound cooperative market production portfolio
    scene-market-party-handoff  Replay-verified cooperative campaign handoff across save, league and export
    scene-market-party-balance  Replay-derived cooperative role balance audit for playable market games
    scene-market-party-vault  Optimistic, source-bound offline cooperative save slots
    scene-market-party-vault-history  Replay-verified revision history and recovery for cooperative market save slot
    scene-market  Play earned-currency trading, crafting and delivery quests
    scene-tiles  Play authored grid movement/collision and replay scene saves
    scene-push  Source-bound push-block puzzles on the canonical scene tile runtime
    scene-push-play  Interactive JSON-line crate puzzles with verified durable checkpoints
    scene-push-accept  Independent source-to-play-to-restart-to-export push-puzzle acceptance
    scene-tiles-route  Solve collision-aware replayable tile game routes
    scene-achievements  Earn replay-verified authored scene milestones
    scene-npc  Play authored NPC itineraries, choices and earned scene endings
    scene-npc-solve  Find bounded replayable routes through NPC dialogue
    scene-npc-play  Play offline NPC encounters interactively with checkpoints
    scene-atlas  Explore fog-of-war maps, legal known routes and portable replay
    scene-consequences  Inspect replay-derived mission choices and endings
    scene-mission  Play authored mission DAG and branching choices over scenes
    scene-mission-play  Interactively play authored missions with replayable checkpoints
    scene-mission-board  Inspect replay-derived mission objectives and legal actions
    scene-mission-author  Transactionally edit authored missions and preview play
    scene-mission-route  Solve replayable authored mission ending paths
    scene-mission-assist  Offer replay-proven non-mutating mission hints\n    scene-mission-liveness  Find replayable authored mission softlocks\n    scene-mission-accept  Verify authored endings through playable export
    scene-mission-timeline  Play replay-verified offline mission checkpoints
    scene-mission-league  Rank completed source-bound mission replays offline
    scene-mission-league-author  Transactionally edit and preview league scoring
    scene-escort  Play source-bound convoy deliveries, save/replay and export
    scene-escort-author  Transactionally edit and preview escort missions
    scene-escort-solve  Find replay-proven safe convoy routes with bounded search
    scene-escort-play  Interactively play and checkpoint offline convoy deliveries
    game        Build a playable Godot project from a natural-language brief
                game <brief> [--out DIR] [--overwrite]
                    [--playtest off|auto|require] [--max-rounds N] [--json]
    forge       Blueprint compilation and materialization
    test        Run test suites
    dev         Developer CLI (scaffold, wizard, health, visualize)
    eras        List GameForge era dialects
    generations List hardware generations
    plan        Jeeves BuildPlan for a vision / era
    cockpit     Durable creator steering (BIND, SNAPSHOT --out, RESTORE)
    walk        Prove spawn→extract on the emitted door graph
                (--mode thermal, --seed S, --all-eras, --steps, --json)
    doctor      Check forge prerequisites (eras, walk smoke, output dir, Godot)
    creator     Canonical typed creator command surface (create/edit/test/preview/export)
    contracts   Show the shared API/CLI feature-parity contract
    capabilities Show the stable machine-readable capability manifest
                Use `capabilities --lifecycle` for resolvable/loaded status
                Use `capabilities --plane-audit` for the F-15 plane audit
                Use `capabilities --boot-audit` for the genesis/BOOT_PHASES audit
                Use `capabilities --export-audit` for manifest export drift
                Use `capabilities --route-audit` for main-router API_ROUTES drift
                Use `capabilities --hmac-audit` for HMAC open-prefix vs API_ROUTES drift
                Use `capabilities --cli-audit` for developer CLI vs CLI_COMMANDS drift
                Use `capabilities --template-audit` for scaffold TEMPLATES drift
                Use `capabilities --sidecar-audit` for GameForge/command sidecar routes
                Use `capabilities --domain-audit` for gate-domain vs API_ROUTES mapping
                Use `capabilities --cortex-audit` for unmounted cortex register_routes
                Use `capabilities --mounted-audit` for create_app swarm/cockpit mounts
                Use `capabilities --main-cli-audit` for python -m skeleton help vs dispatch
                Use `capabilities --app-audit` for create_app inline GET / and /cortex/status
                Use `capabilities --charter-audit` for require_charter domain/action pairs
                Use `capabilities --contract-audit` for CommandSpec vs runtime register
                Use `capabilities --live-hmac-audit` for HMAC prefixes vs live handlers
                Use `capabilities --nested-audit` for nested include_router mounts
                Use `capabilities --env-audit` for SKELETON_OWN / HMAC env flags
                Use `capabilities --view-audit` for capability-view flag inventory
                Use `capabilities --idempotency-audit` for IdempotencyGuard handlers
                Use `capabilities --seal-audit` for live require_seal versus HMAC open
                Use `capabilities --admit-audit` for WriteAdmit mutating methods
                Use `capabilities --limit-audit` for SKELETON_GATE_* body/header limits
                Use `capabilities --shared-audit` for status/config shared-command mapping
                Use `capabilities --stack-audit` for install_gate middleware order
                Use `capabilities --allow-audit` for MATERIALISE_TARGETS / curve allow-lists
                Use `capabilities --version-audit` for advertised version identity
                Use `capabilities --authz-audit` for mutating vs auth_required
                Use `capabilities --dev-audit` for opt-in public-dev HMAC prefixes
                Use `capabilities --token-audit` for SKELETON_PUBLIC_DEV_SURFACES tokens
                Use `capabilities --mode-audit` for SessionMode core vs llm_core identity
                Use `capabilities --codename-audit` for advertised codename identity
                Use `capabilities --cver-audit` for command CONTRACT_VERSION identity
                Use `capabilities --ttl-audit` for HMAC/idempotency TTL identity
    combat      Run and replay deterministic offline turn combat encounters
    combat-contract  Play, checkpoint and export earned offline combat missions
    combat-contract-author  Transactionally edit and preview combat missions
    combat-contract-play  Play interactive offline combat mission objectives
    combat-contract-solve  Find replayable earned combat mission routes
    combat-delivery-accept  Verify original combat package against playable acceptance
    combat-contract-package  Build, verify and play portable original combat games
    arena-terrain  Generate and verify original playable tactical geometry
    combat-arena    Play source-bound tactical grid combat with offline replay
    quest-factions-accept  Replay-verify full faction quest production acceptance
    quest-factions-play  Interactively play and checkpoint offline faction quests
    quest-factions-author  Transactionally author and preview faction consequences
    quest-factions-route  Solve replayable faction-gated quest endings
    quest-factions  Play NPC faction reputation and earned quest consequences
    quest-author  Edit original quest source and preview offline gameplay
    quest-expedition  Play authored NPC/choice/crafting quest over combat
    quest-expedition-play  Play NPC crafting and combat quests with offline checkpoints
    quest-inventory  Audit earned NPC gifts and crafting inventory provenance
    quest-decisions  Preview and apply source-bound playable NPC/crafting decisions
    quest-checkpoints  Replay historical quest saves and alternate endings
    quest-expedition-route  Find replayable NPC crafting and combat ending routes
    quest-campaign-play  Interactively play and resume earned chapter campaigns
    quest-campaign-route  Solve and replay authored multi-chapter campaign completion
    quest-campaign-accept  Verify edited campaign, earned victory and portable replay
    game-vertical-accept  Replay-verify complete playable quests and crafting games
    quest-campaign  Play, resume, verify and export multi-chapter offline quests
    quest-campaign-author  Edit and preview replay-verified chapter campaigns
    arena-forge-author  Atomically edit and preview tactical crafting sources
    arena-forge-solve  Solve bounded equipment and combat routes
    arena-forge    Play earned salvage, equipment crafting and tactical arenas
    combat-checkpoints  Replay and fork portable expedition checkpoints
    combat-expedition-playbook  Build and verify portable playable victories
    combat-expedition-audit  Audit earned rewards, spending and save branches
    combat-expedition-solve  Find replayable bounded expedition routes
    combat-expedition  Play original multi-arena campaigns with earned inventory
    tournament-author  Edit and preview replay-verifiable tournament brackets
    combat-league-author  Transactionally edit and preview offline league
    combat-career-roadmap  Replay bounded multi-season training and portable career saves
    combat-career-advice  Compare bounded replayed training choices
    combat-career-author  Transactionally edit and preview coaching careers
    combat-career  Play, train, save and replay a multi-season coaching career
    combat-league  Play source-bound offline eight-entrant combat league
    combat-tournament  Play and replay a source-bound four-entrant bracket
    combat-campaign-timeline  Audit player turns, earned rewards and portable saves
    combat-campaign-player  Play a human-controlled offline combat campaign with earned rewards and replay
    combat-campaign  Run a replay-verifiable offline combat campaign with durable inter-encounter state
    combat-balance  Analyze source-bound combat victory and verify replay receipts
    combat-drill-solve  Find replayable bounded shortest combat lesson solutions
    combat-stamina  Play tactical stamina, author and export verified saves
    combat-drill  Play, grade, resume and verify offline combat lessons
    combat-inspect  Inspect verified combat timelines and compare saved branches
    campaign    Play an original deterministic offline grid campaign
    world-laptop Laptop-first typed prompt, reviewed world, builder handoff and replay
    world-canon  Original-world prompt, typed edit, proof and offline playable compile
    world-assets Original asset briefs, reviewed provenance and engine compilation
    world-timeline Source-bound causal chronology and temporal playable handoff
    world-bundle Verified offline playable HTML and era engine handoff
    world-plan   Typed source-derived production DAG, review and compilation
    world-editor Offline browser scene editing with source-leased JSON export
    world-route  Reviewed world navigation, deterministic route replay and playable handoff
    world-cast   Original NPC presence, authored dialogue and playable continuity
    world-experience Unified reviewed world, cast and route offline playable
    world-revision Field-level causal impact review and source-verified HTML5 handoff
    world-assurance Integrated exact-source gameplay assurance and HTML5 handoff
    world-invariants Exhaustive authored world-state proof and playable handoff
    world-scenario Authored gameplay acceptance and source-leased HTML5 proof
    world-choice-impact Source-derived choice consequences and playable proof
    world-playtest Bounded choice-coverage proof and verified playable QA handoff
    world-migrate Reviewed source-revision save migration with exact replay proof
    world-field-journal Player-authored source-leased notes and verified HTML5 handoff
    world-weather Reviewed deterministic scene weather and replay handoff
    world-advisories Reviewed scene content notices and masked HTML5 player handoff
    world-epilogues Reviewed original ending closure and replay-verified HTML5 handoff
    world-fork    Reviewed alternate save fork, causal replay and HTML5 handoff
    world-session Source-verified offline play, save, resume and checkpoint replay
    world-quest  Original objective authoring, earned consequences and quest proof
    world-counterfactual Reviewed alternate endings from actual player choices
    world-lore   Original lore canon, branch contradiction proof and player reveal
    world-factions Reviewed faction reputation, earned choices and playable handoff
    world-evidence Original clue discovery, reviewed canon and replayed playable
    world-integrated Verified cast, route, promises and private context playable
    world-context Bounded source-leased author note custody and replay
    world-promises Reviewed narrative promises, closure proof and playable handoff
    world-knowledge Reviewed NPC fact provenance, disclosure proof and playable handoff
    world-studio-engine Reviewed original worlds to typed engine recipes
    world-studio Reviewed multi-plane original-world playable assembly
    world-director Unified reviewed chapters, cinematics and HTML5 playable
    world-chapters Reviewed original chapter/act structure and playable navigation
    world-cinematics Reviewed original scene storyboards, engine cues and HTML5 playable
    world-pacing Reviewed dramatic arcs, climax witnesses and playable proof
    world-accessibility Reviewed accessible narration and keyboard gameplay
    world-localization Reviewed original language editions and offline playable
    world-rumors Reviewed causal NPC information flow and playable handoff
    world-testimony Reviewed NPC witnesses, contradiction proof and playable handoff
    world-relationships Reviewed original NPC trust, replay and playable handoff
    world-events Reviewed one-shot world events, flag closure and HTML5 handoff
    world-puzzles Reviewed original scene riddles and verified choice-gated gameplay
    world-inventory Reviewed original item effects and source-bound HTML5 playable
    world-npc-schedule Reviewed NPC itineraries, temporal proof and offline playable
    world-portals Reviewed multi-world original portal journeys and playable handoff
    world-atlas  Reviewed original regions, choice-bound travel and playable handoff
    world-dialogue-locales Reviewed original branching NPC language editions
    world-dialogue-transcript Private source-leased NPC conversation custody and replay
    world-interaction Unified original economy, character arcs and dialogue HTML5
    world-dialogue Reviewed interactive NPC dialogue and atomic world-choice handoff
    world-character-arcs Reviewed original character transformation and ending proof
    world-economy Reviewed bounded resources, deterministic replay and HTML5 handoff
    world-tools Static read-only typed Jeeves world tool registry and previews
    quest       Offline source-bound quest transactions (inspect/run/verify)
    invoke      Execute the versioned unified request envelope
    command     Execute a shared command: command <name> ['{...json...}']
    status      Shared runtime status command
    config      Shared non-secret configuration command
    help        Show this help message
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional


def _cmd_contracts(_rest: List[str]) -> int:
    from skeleton.application import parity_matrix

    print(json.dumps(parity_matrix(), indent=2, default=str))
    return 0


def _cmd_capabilities(rest: List[str]) -> int:
    from skeleton.application import (
        capability_lifecycle_snapshot,
        capability_manifest,
        export_audit_snapshot,
        genesis_boot_audit_snapshot,
        plane_audit_snapshot,
        api_route_audit_snapshot,
        hmac_open_audit_snapshot,
        developer_cli_audit_snapshot,
        template_audit_snapshot,
        sidecar_route_audit_snapshot,
        gate_domain_audit_snapshot,
        cortex_route_audit_snapshot,
        mounted_route_audit_snapshot,
        main_cli_audit_snapshot,
        app_route_audit_snapshot,
        charter_audit_snapshot,
        contract_audit_snapshot,
        live_hmac_audit_snapshot,
        nested_router_audit_snapshot,
        env_flag_audit_snapshot,
        capability_view_audit_snapshot,
        idempotency_audit_snapshot,
        seal_audit_snapshot,
        admit_write_audit_snapshot,
        gate_limit_audit_snapshot,
        cli_shared_audit_snapshot,
        gate_stack_audit_snapshot,
        allow_list_audit_snapshot,
        version_audit_snapshot,
        authz_audit_snapshot,
        open_dev_audit_snapshot,
        dev_token_audit_snapshot,
        session_mode_audit_snapshot,
        codename_audit_snapshot,
        contract_version_audit_snapshot,
        ttl_audit_snapshot,
    )

    flags = {item.strip().lower() for item in rest if item.strip()}
    aliases = {
        "lifecycle": {"--lifecycle", "lifecycle"},
        "plane_audit": {"--plane-audit", "plane-audit", "--plane_audit", "plane_audit"},
        "boot_audit": {"--boot-audit", "boot-audit", "--boot_audit", "boot_audit"},
        "export_audit": {"--export-audit", "export-audit", "--export_audit", "export_audit"},
        "route_audit": {"--route-audit", "route-audit", "--route_audit", "route_audit"},
        "hmac_audit": {"--hmac-audit", "hmac-audit", "--hmac_audit", "hmac_audit"},
        "cli_audit": {"--cli-audit", "cli-audit", "--cli_audit", "cli_audit"},
        "template_audit": {"--template-audit", "template-audit", "--template_audit", "template_audit"},
        "sidecar_audit": {"--sidecar-audit", "sidecar-audit", "--sidecar_audit", "sidecar_audit"},
        "domain_audit": {"--domain-audit", "domain-audit", "--domain_audit", "domain_audit"},
        "cortex_audit": {"--cortex-audit", "cortex-audit", "--cortex_audit", "cortex_audit"},
        "mounted_audit": {"--mounted-audit", "mounted-audit", "--mounted_audit", "mounted_audit"},
        "main_cli_audit": {"--main-cli-audit", "main-cli-audit", "--main_cli_audit", "main_cli_audit"},
        "app_audit": {"--app-audit", "app-audit", "--app_audit", "app_audit"},
        "charter_audit": {"--charter-audit", "charter-audit", "--charter_audit", "charter_audit"},
        "contract_audit": {"--contract-audit", "contract-audit", "--contract_audit", "contract_audit"},
        "live_hmac_audit": {"--live-hmac-audit", "live-hmac-audit", "--live_hmac_audit", "live_hmac_audit"},
        "nested_audit": {"--nested-audit", "nested-audit", "--nested_audit", "nested_audit"},
        "env_audit": {"--env-audit", "env-audit", "--env_audit", "env_audit"},
        "view_audit": {"--view-audit", "view-audit", "--view_audit", "view_audit"},
        "idempotency_audit": {"--idempotency-audit", "idempotency-audit", "--idempotency_audit", "idempotency_audit"},
        "seal_audit": {"--seal-audit", "seal-audit", "--seal_audit", "seal_audit"},
        "admit_audit": {"--admit-audit", "admit-audit", "--admit_audit", "admit_audit"},
        "limit_audit": {"--limit-audit", "limit-audit", "--limit_audit", "limit_audit"},
        "shared_audit": {"--shared-audit", "shared-audit", "--shared_audit", "shared_audit"},
        "stack_audit": {"--stack-audit", "stack-audit", "--stack_audit", "stack_audit"},
        "allow_audit": {"--allow-audit", "allow-audit", "--allow_audit", "allow_audit"},
        "version_audit": {"--version-audit", "version-audit", "--version_audit", "version_audit"},
        "authz_audit": {"--authz-audit", "authz-audit", "--authz_audit", "authz_audit"},
        "dev_audit": {"--dev-audit", "dev-audit", "--dev_audit", "dev_audit"},
        "token_audit": {"--token-audit", "token-audit", "--token_audit", "token_audit"},
        "mode_audit": {"--mode-audit", "mode-audit", "--mode_audit", "mode_audit"},
        "codename_audit": {"--codename-audit", "codename-audit", "--codename_audit", "codename_audit"},
        "cver_audit": {"--cver-audit", "cver-audit", "--cver_audit", "cver_audit"},
        "ttl_audit": {"--ttl-audit", "ttl-audit", "--ttl_audit", "ttl_audit"},
    }
    allowed = set().union(*aliases.values())
    unknown = flags - allowed
    if unknown:
        print(f"Unknown capabilities option: {sorted(unknown)[0]}")
        return 2
    selected = [name for name, names in aliases.items() if flags & names]
    if len(selected) > 1:
        print(f"{' and '.join(selected)} are mutually exclusive")
        return 2
    view = selected[0] if selected else ""
    if view == "ttl_audit":
        payload = ttl_audit_snapshot()
    elif view == "cver_audit":
        payload = contract_version_audit_snapshot()
    elif view == "codename_audit":
        payload = codename_audit_snapshot()
    elif view == "mode_audit":
        payload = session_mode_audit_snapshot()
    elif view == "token_audit":
        payload = dev_token_audit_snapshot()
    elif view == "dev_audit":
        payload = open_dev_audit_snapshot()
    elif view == "authz_audit":
        payload = authz_audit_snapshot()
    elif view == "version_audit":
        payload = version_audit_snapshot()
    elif view == "allow_audit":
        payload = allow_list_audit_snapshot()
    elif view == "stack_audit":
        payload = gate_stack_audit_snapshot()
    elif view == "shared_audit":
        payload = cli_shared_audit_snapshot()
    elif view == "limit_audit":
        payload = gate_limit_audit_snapshot()
    elif view == "admit_audit":
        payload = admit_write_audit_snapshot()
    elif view == "seal_audit":
        payload = seal_audit_snapshot()
    elif view == "idempotency_audit":
        payload = idempotency_audit_snapshot()
    elif view == "view_audit":
        payload = capability_view_audit_snapshot()
    elif view == "env_audit":
        payload = env_flag_audit_snapshot()
    elif view == "nested_audit":
        payload = nested_router_audit_snapshot()
    elif view == "live_hmac_audit":
        payload = live_hmac_audit_snapshot()
    elif view == "contract_audit":
        payload = contract_audit_snapshot()
    elif view == "charter_audit":
        payload = charter_audit_snapshot()
    elif view == "app_audit":
        payload = app_route_audit_snapshot()
    elif view == "main_cli_audit":
        payload = main_cli_audit_snapshot()
    elif view == "mounted_audit":
        payload = mounted_route_audit_snapshot()
    elif view == "cortex_audit":
        payload = cortex_route_audit_snapshot()
    elif view == "domain_audit":
        payload = gate_domain_audit_snapshot()
    elif view == "sidecar_audit":
        payload = sidecar_route_audit_snapshot()
    elif view == "template_audit":
        payload = template_audit_snapshot()
    elif view == "cli_audit":
        payload = developer_cli_audit_snapshot()
    elif view == "hmac_audit":
        payload = hmac_open_audit_snapshot()
    elif view == "route_audit":
        payload = api_route_audit_snapshot()
    elif view == "export_audit":
        payload = export_audit_snapshot()
    elif view == "boot_audit":
        payload = genesis_boot_audit_snapshot()
    elif view == "plane_audit":
        payload = plane_audit_snapshot()
    elif view == "lifecycle":
        payload = capability_lifecycle_snapshot()
    else:
        payload = capability_manifest()
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _boot_runtime_if_needed(state: Any, command: str) -> None:
    if command in {"run", "tool", "memory", "admin", "retrieve", "plan", "evidence"} and state.genesis is None:
        from skeleton.genesis import Genesis

        state.wire_from_genesis(Genesis(seed=42).boot())


def _print_contract_error(*, command: str, code: str, message: str, exit_code: int, correlation_id: str = "") -> int:
    from skeleton.application import CONTRACT_VERSION, SCHEMA_VERSION, SUPPORTED_MODE

    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "command": command,
        "ok": False,
        "mode": SUPPORTED_MODE,
        "correlation_id": correlation_id,
        "error": {"code": code, "message": message},
    }
    print(json.dumps(payload, indent=2))
    return exit_code


def _cmd_invoke(rest: List[str]) -> int:
    from skeleton.api.server import get_state
    from skeleton.application import CommandError, invoke_unified, normalize_request

    if not rest:
        return _print_contract_error(
            command="",
            code="invalid_argument",
            message="invoke envelope JSON is required",
            exit_code=2,
        )
    raw_payload = " ".join(rest).strip()
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError:
        return _print_contract_error(
            command="",
            code="invalid_argument",
            message="invalid JSON payload",
            exit_code=2,
        )
    if not isinstance(decoded, dict):
        return _print_contract_error(
            command="",
            code="invalid_argument",
            message="invoke envelope must be a JSON object",
            exit_code=2,
        )

    try:
        request = normalize_request(decoded)
    except CommandError:
        result = invoke_unified(None, decoded)
        print(json.dumps(result.to_payload(), indent=2, default=str))
        return result.exit_code

    state = get_state()
    _boot_runtime_if_needed(state, request.command)
    result = invoke_unified(state, decoded)
    print(json.dumps(result.to_payload(), indent=2, default=str))
    return result.exit_code


def _cmd_shared_command(rest: List[str]) -> int:
    from skeleton.api.server import get_state
    from skeleton.application import build_runtime_command_service

    if not rest:
        return _print_contract_error(
            command="",
            code="invalid_command",
            message="command name is required",
            exit_code=2,
        )

    command = rest[0].strip().lower()
    payload = {}
    if len(rest) > 1:
        raw_payload = " ".join(rest[1:]).strip()
        try:
            decoded = json.loads(raw_payload)
        except json.JSONDecodeError:
            return _print_contract_error(
                command=command,
                code="invalid_argument",
                message="invalid JSON payload",
                exit_code=2,
            )
        if not isinstance(decoded, dict):
            return _print_contract_error(
                command=command,
                code="invalid_argument",
                message="command payload must be a JSON object",
                exit_code=2,
            )
        payload = decoded

    state = get_state()
    _boot_runtime_if_needed(state, command)

    result = build_runtime_command_service(state).execute(command, payload)
    print(json.dumps(result.to_payload(), indent=2, default=str))
    return result.exit_code


def _cmd_eras(rest: List[str]) -> int:
    from skeleton.forge.walk_cli import run_eras
    return run_eras(rest)


def _cmd_generations(_rest: List[str]) -> int:
    from skeleton.forge.hardware import catalog
    for g in catalog():
        print(f"{g['key']:10} {g['label']:16} {g['viewport'][0]}x{g['viewport'][1]}  {g['tagline']}")
    return 0


def _cmd_plan(rest: List[str]) -> int:
    from skeleton.cortex.live import live_jeeves, persist
    vision = " ".join(rest).strip()
    out = live_jeeves().plan_build(vision=vision)
    persist()
    print(json.dumps(out, indent=2, default=str))
    return 0


def _cmd_cockpit(rest: List[str]) -> int:
    """Operate the persisted, versioned local creator steering state."""
    from pathlib import Path
    from skeleton.context.cockpit import Cockpit, CockpitError
    from skeleton.context.operator_state import (
        capture_steering, read_steering, restore_cockpit, write_steering,
    )
    try:
        if rest and rest[0].upper() == "RESTORE":
            if len(rest) != 2:
                raise ValueError("usage: cockpit RESTORE <snapshot.json>")
            incoming = read_steering(Path(rest[1]))
            if incoming is None:
                raise ValueError("cockpit snapshot does not exist")
            # Recovery must still work after a corrupt local state.
            write_steering(incoming)
            out = {"ok": True, "verb": "RESTORE",
                   "result": restore_cockpit(incoming).snapshot()}
        else:
            saved = read_steering()
            cockpit = restore_cockpit(saved) if saved else Cockpit()
            if rest and rest[0].upper() == "SNAPSHOT" and len(rest) == 3 and rest[1] == "--out":
                location = write_steering(
                    capture_steering(cockpit, era_bound=bool(saved and saved["era_bound"])),
                    Path(rest[2]),
                )
                out = {"ok": True, "verb": "SNAPSHOT",
                       "path": str(location), "result": cockpit.snapshot()}
            elif rest and rest[0].upper() == "SNAPSHOT" and len(rest) != 1:
                raise ValueError("usage: cockpit SNAPSHOT [--out snapshot.json]")
            else:
                out = cockpit.apply(" ".join(rest).strip())
                verb = out["verb"]
                if verb in {"BIND", "SET", "LERP", "BLEND", "DETECT"}:
                    bound = bool(saved and saved["era_bound"])
                    if verb in {"DETECT", "LERP"} or (
                        verb == "BIND" and len(rest) > 1 and rest[1].upper() == "ERA"
                    ):
                        bound = True
                    elif verb == "BLEND":
                        bound = False
                    write_steering(capture_steering(cockpit, era_bound=bound))
    except (OSError, ValueError, CockpitError) as exc:
        print(f"cockpit: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0


def _parse_walk_args(rest: List[str]):
    era = "extraction_now"
    blend = None
    t = 0.5
    as_json = False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--era" and i + 1 < len(rest):
            era = rest[i + 1]; i += 2
        elif a == "--blend" and i + 2 < len(rest):
            blend = (rest[i + 1], rest[i + 2]); i += 3
        elif a == "--t" and i + 1 < len(rest):
            t = float(rest[i + 1]); i += 2
        elif a == "--json":
            as_json = True; i += 1
        else:
            i += 1
    return era, blend, t, as_json


def _cmd_walk(rest: List[str]) -> int:
    from skeleton.forge.walk_cli import run_walk
    return run_walk(rest)


def _cmd_doctor(rest: List[str]) -> int:
    from skeleton.forge.walk_cli import run_doctor
    return run_doctor(rest)


def _load_run_answers(source: str, *, file_path: bool = False) -> Dict[str, str]:
    """Read bounded questionnaire answers (inline JSON, @file or --answers-file).

    Reject misspelled beat names and choices instead of silently discarding
    operator intent. Brief facets are intentionally free-form strings.
    """
    from pathlib import Path
    from skeleton.context.questionnaire import validate_answers

    # Backward-compatible with the existing creator CLI's --answers PATH.
    legacy_file = False
    if not file_path and not source.startswith("@") and not source.lstrip().startswith(("{", "[")):
        try:
            legacy_file = Path(source).expanduser().is_file()
        except (OSError, ValueError):
            legacy_file = False
    if file_path or source.startswith("@") or legacy_file:
        path = Path(source[1:] if source.startswith("@") and not file_path else source).expanduser()
        try:
            if path.stat().st_size > 65_536:
                raise ValueError("answers file exceeds 64 KiB")
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read answers file: {exc}") from exc
    else:
        raw = source
    if len(raw.encode("utf-8")) > 65_536:
        raise ValueError("answers JSON exceeds 64 KiB")
    try:
        answers = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid answers JSON: {exc.msg}") from exc
    if not isinstance(answers, dict):
        raise ValueError("answers must be a JSON object mapping strings to strings")
    return validate_answers(answers)


def _parse_run_args(rest: List[str]):
    vision_parts: List[str] = []
    era = None
    out = None
    overwrite = False
    as_json = False
    blend = None
    t = 0.5
    generation = None
    answers: Dict[str, str] = {}
    playtest = None
    repair_mode = "apply"
    archetype = None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("--era", "--out", "--generation", "--answers", "--answers-file",
                 "--playtest", "--repair-mode", "--archetype", "--t"):
            if i + 1 >= len(rest):
                raise ValueError(f"{a} requires a value")
            value = rest[i + 1]
            if a == "--era":
                era = value
            elif a == "--out":
                out = value
            elif a == "--generation":
                generation = value
            elif a == "--answers":
                answers = _load_run_answers(value)
            elif a == "--answers-file":
                answers = _load_run_answers(value, file_path=True)
            elif a == "--playtest":
                if value not in ("off", "auto", "require"):
                    raise ValueError("--playtest must be off, auto or require")
                playtest = value
            elif a == "--repair-mode":
                if value not in ("apply", "suggest"):
                    raise ValueError("--repair-mode must be apply or suggest")
                repair_mode = value
            elif a == "--archetype":
                archetype = value
            else:
                try:
                    t = float(value)
                except ValueError as exc:
                    raise ValueError("--t must be a finite number in [0, 1]") from exc
                import math
                if not math.isfinite(t) or not 0 <= t <= 1:
                    raise ValueError("--t must be a finite number in [0, 1]")
            i += 2
        elif a in ("--overwrite", "--json"):
            if a == "--overwrite":
                overwrite = True
            else:
                as_json = True
            i += 1
        elif a == "--blend":
            if i + 2 >= len(rest) or rest[i + 1].startswith("--") or rest[i + 2].startswith("--"):
                raise ValueError("--blend requires two era names")
            blend = (rest[i + 1], rest[i + 2])
            i += 3
        elif a.startswith("-"):
            raise ValueError(f"unknown run option: {a}")
        else:
            vision_parts.append(a)
            i += 1
    if blend is None and "--t" in rest:
        raise ValueError("--t requires --blend")
    blend_arg = tuple(blend) + (t,) if blend else None
    return (" ".join(vision_parts).strip(), era, out, overwrite, as_json,
            blend_arg, generation, answers, playtest, repair_mode, archetype)


def _cmd_gameforge_run(rest: List[str]) -> int:
    from skeleton.context.pipeline import GameForgeRun
    from skeleton.context.operator_state import read_steering, restore_cockpit
    if any(arg in ("--help", "-h") for arg in rest):
        print("Usage: python -m skeleton run <vision> [--answers JSON|@FILE] "
              "[--answers-file FILE] [--era ID] [--archetype NAME] [--out DIR] "
              "[--overwrite] [--playtest off|auto|require] "
              "[--repair-mode apply|suggest] [--blend ERA1 ERA2 --t 0..1] "
              "[--generation ID] [--json]")
        print("Operator pipeline only. Playable builds use: python -m skeleton game <brief>")
        return 0
    try:
        (vision, era, out, overwrite, as_json, blend, generation, answers,
         playtest, repair_mode, archetype) = _parse_run_args(rest)
        saved = read_steering()
    except (ValueError, OSError) as exc:
        print(f"run: {exc}", file=sys.stderr)
        return 2
    if not rest:
        from skeleton.genesis import Genesis
        genesis = Genesis(seed=42).boot()
        print("Skeleton runtime booted.")
        print(f"Handles: {list(genesis.handles.keys())}")
        return 0
    cockpit = restore_cockpit(saved) if saved else None
    explicit = era is not None or blend is not None
    if not explicit and saved:
        if saved["era_bound"]:
            era = saved["tensor"]["era"]
        elif saved["blend"]:
            blend = tuple(saved["blend"])
    # Questionnaire axes are authoritative unless an operator explicitly
    # pinned an era; persisted default axes must not erase voted intake.
    operator_tensor = (
        cockpit.tensor if cockpit is not None and not explicit
        and blend is None and (not answers or bool(saved and saved["era_bound"]))
        else None
    )
    try:
        payload = GameForgeRun.live(cockpit=cockpit).execute(
            vision, era=era, archetype=archetype, answers=answers,
            project_root=out, overwrite=overwrite, target="godot",
            blend=blend, generation=generation, playtest=playtest,
            repair_mode=repair_mode, operator_tensor=operator_tensor,
        )
    except ValueError as exc:
        print(f"run: {exc}", file=sys.stderr)
        return 2
    if as_json:
        keys = ("succeeded", "era", "mass", "complete", "sim", "project",
                "forge", "intake", "playtest", "run", "source_manifest")
        slim = {k: payload[k] for k in keys if k in payload}
        slim["failed_stages"] = [s for s in (payload.get("run") or {}).get("stages", [])
                                 if s.get("status") == "FAILED"]
        print(json.dumps(slim, indent=2, default=str))
    else:
        check = payload.get("playtest")
        check_result = (check.get("status", check.get("passed")) if isinstance(check, dict)
                        else ("off" if playtest in (None, "off") else "not-reached"))
        print(f"era={payload.get('era')} mass={payload.get('mass')} "
              f"sim={(payload.get('sim') or {}).get('passed')} "
              f"files={(payload.get('forge') or {}).get('file_count')} "
              f"playtest={check_result}")
        if payload.get("project"):
            print("wrote", payload["project"]["root"])
        for stage in (payload.get("run") or {}).get("stages", []):
            if stage.get("status") == "FAILED":
                print(f"FAILED stage={stage.get('name')}: "
                      f"{stage.get('error') or stage.get('gate_failure')}", file=sys.stderr)
    return 0 if payload.get("succeeded") else 1



def _cmd_creator(rest: List[str]) -> int:
    """Compile one CLI creator request into the canonical B014 envelope."""
    from skeleton.forge.creator.command_surface import (
        CreatorCommandError,
        creator_cli_payload,
    )

    try:
        payload = creator_cli_payload(rest)
    except CreatorCommandError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": exc.code,
                    "message": str(exc),
                    "context": dict(getattr(exc, "context", {})),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_test(_rest: List[str]) -> int:
    """Run the configured pytest suite, with unittest discovery as a fallback."""
    try:
        import pytest
    except ImportError:
        import unittest
        suite = unittest.TestLoader().discover("skeleton/testing", pattern="test_*.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    return int(pytest.main(["skeleton/testing", "-ra"]))


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 0

    cmd = args[0]
    rest = args[1:]
    if cmd == "app":
        from skeleton.app.cli import run_app_cli
        return run_app_cli(rest)
    if cmd in ("ready", "product", "health", "next"):
        from skeleton.organism.operator_cli import run_operator_cli
        return run_operator_cli(cmd, rest)
    if cmd in ("wiki", "seed", "caps", "lattice", "pulse", "orch", "season", "scoreboard", "hot", "coverage", "decade", "bank", "switch", "witness", "gov", "cage", "rot", "fieldcov", "enact", "day", "week", "calendar", "conductor", "ctx", "live", "observe", "stacks", "mix", "satellites", "path", "bound", "fieldwalk", "dump", "orgwalk", "sleep", "forget", "helix", "recall"):
        from skeleton.organism.operator_cli import run_operator_cli
        return run_operator_cli(cmd, rest)
    if cmd == "run": return _cmd_gameforge_run(rest)
    if cmd == "scene-escort":
        from skeleton.game.gameplay.scene_escort import cli as escort_cli
        return escort_cli(rest)
    if cmd == "scene-escort-play":
        from skeleton.game.gameplay.scene_escort_interactive import cli as escort_play_cli
        return escort_play_cli(rest)
    if cmd == "scene-escort-solve":
        from skeleton.game.gameplay.scene_escort_solver import cli as escort_solver_cli
        return escort_solver_cli(rest)
    if cmd == "scene-escort-author":
        from skeleton.game.gameplay.scene_escort_author import cli as escort_author_cli
        return escort_author_cli(rest)
    if cmd == "scene-mission-league-author":
        from skeleton.game.gameplay.scene_mission_league_author import cli as league_author_cli
        return league_author_cli(rest)
    if cmd == "scene-mission-league":
        from skeleton.game.gameplay.scene_mission_league import cli as league_cli
        return league_cli(rest)
    if cmd == "scene-mission-timeline":
        from skeleton.game.gameplay.scene_mission_timeline import cli as timeline_cli
        return timeline_cli(rest)
    if cmd == "scene-mission-assist":
        from skeleton.game.gameplay.scene_mission_assistance import cli as assist_cli
        return assist_cli(rest)
    if cmd == "scene-mission-liveness":
        from skeleton.game.gameplay.scene_mission_liveness import cli as liveness_cli
        return liveness_cli(rest)
    if cmd == "scene-mission-accept":
        from skeleton.game.gameplay.scene_mission_acceptance import cli as accept_cli
        return accept_cli(rest)
    if cmd == "scene-mission-route":
        from skeleton.game.gameplay.scene_mission_solver import cli as route_cli
        return route_cli(rest)
    if cmd == "scene-consequences":
        from skeleton.game.gameplay.scene_mission_consequences import cli as consequences_cli
        return consequences_cli(rest)
    if cmd == "scene-mission":
        from skeleton.game.gameplay.scene_mission import cli as mission_cli
        return mission_cli(rest)
    if cmd == "scene-mission-play":
        from skeleton.game.gameplay.scene_mission_interactive import cli as mission_play_cli
        return mission_play_cli(rest)
    if cmd == "scene-mission-board":
        from skeleton.game.gameplay.scene_mission_board import cli as mission_board_cli
        return mission_board_cli(rest)
    if cmd == "scene-mission-author":
        from skeleton.game.gameplay.scene_mission_author import cli as mission_author_cli
        return mission_author_cli(rest)
    if cmd == "scene-author":
        from skeleton.game.gameplay.scene_world_author import cli as scene_author_cli
        return scene_author_cli(rest)
    if cmd == "scene-achievements":
        from skeleton.game.gameplay.scene_achievements import cli as achievements_cli
        return achievements_cli(rest)
    if cmd == "scene-atlas":
        from skeleton.game.gameplay.scene_atlas import cli as atlas_cli
        return atlas_cli(rest)
    if cmd == "scene-circuit-author":
        from skeleton.game.gameplay.scene_circuit_author import cli as circuit_author_cli
        return circuit_author_cli(rest)
    if cmd == "scene-circuit-solve":
        from skeleton.game.gameplay.scene_circuit_solver import cli as circuit_solver_cli
        return circuit_solver_cli(rest)
    if cmd == "scene-circuit":
        from skeleton.game.gameplay.scene_circuit import cli as circuit_cli
        return circuit_cli(rest)
    if cmd == "scene-patrol-solve":
        from skeleton.game.gameplay.scene_guard_patrol_solver import cli as patrol_solver_cli
        return patrol_solver_cli(rest)
    if cmd == "scene-patrol-author":
        from skeleton.game.gameplay.scene_guard_patrol_author import cli as patrol_author_cli
        return patrol_author_cli(rest)
    if cmd == "scene-patrol":
        from skeleton.game.gameplay.scene_guard_patrol import cli as patrol_cli
        return patrol_cli(rest)
    if cmd == "scene-accept":
        from skeleton.game.gameplay.scene_acceptance import cli as accept_cli
        return accept_cli(rest)
    if cmd == "scene-tiles-route":
        from skeleton.game.gameplay.scene_tile_route import cli as scene_tile_route_cli
        return scene_tile_route_cli(rest)
    if cmd == "scene-survival-campaign-author":
        from skeleton.game.gameplay.scene_survival_campaign_author import cli as campaign_author_cli
        return campaign_author_cli(rest)
    if cmd == "scene-survival-campaign-route":
        from skeleton.game.gameplay.scene_survival_campaign_route import cli as campaign_route_cli
        return campaign_route_cli(rest)
    if cmd == "scene-survival-campaign-accept":
        from skeleton.game.gameplay.scene_survival_campaign_acceptance import cli as campaign_accept_cli
        return campaign_accept_cli(rest)
    if cmd == "scene-survival-campaign-play":
        from skeleton.game.gameplay.scene_survival_campaign_interactive import cli as campaign_play_cli
        return campaign_play_cli(rest)
    if cmd == "scene-survival-campaign":
        from skeleton.game.gameplay.scene_survival_campaign import cli as survival_campaign_cli
        return survival_campaign_cli(rest)
    if cmd == "scene-survival-play":
        from skeleton.game.gameplay.scene_tile_survival_interactive import cli as survival_play_cli
        return survival_play_cli(rest)
    if cmd == "scene-survival-author":
        from skeleton.game.gameplay.scene_tile_survival_author import cli as survival_author_cli
        return survival_author_cli(rest)
    if cmd == "scene-survival-route":
        from skeleton.game.gameplay.scene_tile_survival_route import cli as survival_route_cli
        return survival_route_cli(rest)
    if cmd == "scene-survival":
        from skeleton.game.gameplay.scene_tile_survival import cli as scene_survival_cli
        return scene_survival_cli(rest)
    if cmd == "scene-market-accept":
        from skeleton.game.gameplay.scene_market_acceptance import cli as market_accept_cli
        return market_accept_cli(rest)
    if cmd == "scene-market-play":
        from skeleton.game.gameplay.scene_market_interactive import cli as market_play_cli
        return market_play_cli(rest)
    if cmd == "scene-market-author":
        from skeleton.game.gameplay.scene_market_author import cli as market_author_cli
        return market_author_cli(rest)
    if cmd == "scene-market":
        from skeleton.game.gameplay.scene_market import cli as market_cli
        return market_cli(rest)
    if cmd == "scene-circuit-accept":
        from skeleton.game.gameplay.scene_circuit_accept import cli as scene_circuit_accept_cli
        return scene_circuit_accept_cli(rest)
    if cmd == "scene-weather":
        from skeleton.game.gameplay.scene_weather import cli as scene_weather_cli
        return scene_weather_cli(rest)
    if cmd == "scene-weather-author":
        from skeleton.game.gameplay.scene_weather_author import cli as scene_weather_author_cli
        return scene_weather_author_cli(rest)
    if cmd == "scene-weather-play":
        from skeleton.game.gameplay.scene_weather_interactive import cli as scene_weather_interactive_cli
        return scene_weather_interactive_cli(rest)
    if cmd == "scene-weather-board":
        from skeleton.game.gameplay.scene_weather_board import cli as scene_weather_board_cli
        return scene_weather_board_cli(rest)
    if cmd == "scene-weather-route":
        from skeleton.game.gameplay.scene_weather_route import cli as scene_weather_route_cli
        return scene_weather_route_cli(rest)
    if cmd == "scene-weather-accept":
        from skeleton.game.gameplay.scene_weather_acceptance import cli as scene_weather_acceptance_cli
        return scene_weather_acceptance_cli(rest)
    if cmd == "scene-market-fork-play":
        from skeleton.game.gameplay.scene_market_fork_interactive import cli as scene_market_fork_interactive_cli
        return scene_market_fork_interactive_cli(rest)
    if cmd == "scene-market-fork-author":
        from skeleton.game.gameplay.scene_market_fork_author import cli as scene_market_fork_author_cli
        return scene_market_fork_author_cli(rest)
    if cmd == "scene-market-fork-accept":
        from skeleton.game.gameplay.scene_market_fork_acceptance import cli as scene_market_fork_acceptance_cli
        return scene_market_fork_acceptance_cli(rest)
    if cmd == "scene-market-fork":
        from skeleton.game.gameplay.scene_market_fork import cli as scene_market_fork_cli
        return scene_market_fork_cli(rest)
    if cmd == "scene-market-hours":
        from skeleton.game.gameplay.scene_market_hours import cli as scene_market_hours_cli
        return scene_market_hours_cli(rest)
    if cmd == "scene-market-hours-play":
        from skeleton.game.gameplay.scene_market_hours_interactive import cli as scene_market_hours_interactive_cli
        return scene_market_hours_interactive_cli(rest)
    if cmd == "scene-market-hours-accept":
        from skeleton.game.gameplay.scene_market_hours_acceptance import cli as scene_market_hours_acceptance_cli
        return scene_market_hours_acceptance_cli(rest)
    if cmd == "scene-market-contract-play":
        from skeleton.game.gameplay.scene_market_contract_interactive import cli as scene_market_contract_interactive_cli
        return scene_market_contract_interactive_cli(rest)
    if cmd == "scene-market-contract-accept":
        from skeleton.game.gameplay.scene_market_contract_acceptance import cli as scene_market_contract_acceptance_cli
        return scene_market_contract_acceptance_cli(rest)
    if cmd == "scene-market-contract":
        from skeleton.game.gameplay.scene_market_contract import cli as scene_market_contract_cli
        return scene_market_contract_cli(rest)
    if cmd == "scene-market-contract-author":
        from skeleton.game.gameplay.scene_market_contract_author import cli as scene_market_contract_author_cli
        return scene_market_contract_author_cli(rest)
    if cmd == "scene-market-contract-route":
        from skeleton.game.gameplay.scene_market_contract_route import cli as scene_market_contract_route_cli
        return scene_market_contract_route_cli(rest)
    if cmd == "scene-market-route-accept":
        from skeleton.game.gameplay.scene_market_route_acceptance import cli as scene_market_route_acceptance_cli
        return scene_market_route_acceptance_cli(rest)
    if cmd == "scene-market-route":
        from skeleton.game.gameplay.scene_market_route import cli as scene_market_route_cli
        return scene_market_route_cli(rest)
    if cmd == "scene-market-board":
        from skeleton.game.gameplay.scene_market_board import cli as scene_market_board_cli
        return scene_market_board_cli(rest)
    if cmd == "scene-evacuation":
        from skeleton.game.gameplay.scene_evacuation import cli as scene_evacuation_cli
        return scene_evacuation_cli(rest)
    if cmd == "scene-evacuation-board":
        from skeleton.game.gameplay.scene_evacuation_board import cli as scene_evacuation_board_cli
        return scene_evacuation_board_cli(rest)
    if cmd == "scene-evacuation-author":
        from skeleton.game.gameplay.scene_evacuation_author import cli as scene_evacuation_author_cli
        return scene_evacuation_author_cli(rest)
    if cmd == "scene-evacuation-accept":
        from skeleton.game.gameplay.scene_evacuation_acceptance import cli as scene_evacuation_acceptance_cli
        return scene_evacuation_acceptance_cli(rest)
    if cmd == "scene-evacuation-solve":
        from skeleton.game.gameplay.scene_evacuation_solver import cli as scene_evacuation_solver_cli
        return scene_evacuation_solver_cli(rest)
    if cmd == "scene-evacuation-play":
        from skeleton.game.gameplay.scene_evacuation_interactive import cli as scene_evacuation_interactive_cli
        return scene_evacuation_interactive_cli(rest)
    if cmd == "scene-market-party":
        from skeleton.game.gameplay.scene_market_party import cli as scene_market_party_cli
        return scene_market_party_cli(rest)
    if cmd == "scene-market-party-author":
        from skeleton.game.gameplay.scene_market_party_author import cli as scene_market_party_author_cli
        return scene_market_party_author_cli(rest)
    if cmd == "scene-market-party-play":
        from skeleton.game.gameplay.scene_market_party_interactive import cli as scene_market_party_interactive_cli
        return scene_market_party_interactive_cli(rest)
    if cmd == "scene-market-party-board":
        from skeleton.game.gameplay.scene_market_party_board import cli as scene_market_party_board_cli
        return scene_market_party_board_cli(rest)
    if cmd == "scene-market-party-route":
        from skeleton.game.gameplay.scene_market_party_route import cli as scene_market_party_route_cli
        return scene_market_party_route_cli(rest)
    if cmd == "scene-market-party-accept":
        from skeleton.game.gameplay.scene_market_party_acceptance import cli as scene_market_party_acceptance_cli
        return scene_market_party_acceptance_cli(rest)
    if cmd == "scene-market-party-timeline":
        from skeleton.game.gameplay.scene_market_party_timeline import cli as scene_market_party_timeline_cli
        return scene_market_party_timeline_cli(rest)
    if cmd == "scene-market-party-league":
        from skeleton.game.gameplay.scene_market_party_league import cli as scene_market_party_league_cli
        return scene_market_party_league_cli(rest)
    if cmd == "scene-market-party-league-author":
        from skeleton.game.gameplay.scene_market_party_league_author import cli as scene_market_party_league_author_cli
        return scene_market_party_league_author_cli(rest)
    if cmd == "scene-market-party-compare":
        from skeleton.game.gameplay.scene_market_party_compare import cli as scene_market_party_compare_cli
        return scene_market_party_compare_cli(rest)
    if cmd == "scene-market-party-portfolio":
        from skeleton.game.gameplay.scene_market_party_portfolio import cli as scene_market_party_portfolio_cli
        return scene_market_party_portfolio_cli(rest)
    if cmd == "scene-market-party-handoff":
        from skeleton.game.gameplay.scene_market_party_handoff import cli as scene_market_party_handoff_cli
        return scene_market_party_handoff_cli(rest)
    if cmd == "scene-market-party-balance":
        from skeleton.game.gameplay.scene_market_party_balance import cli as scene_market_party_balance_cli
        return scene_market_party_balance_cli(rest)
    if cmd == "scene-market-party-vault":
        from skeleton.game.gameplay.scene_market_party_vault import cli as scene_market_party_vault_cli
        return scene_market_party_vault_cli(rest)
    if cmd == "scene-market-party-vault-history":
        from skeleton.game.gameplay.scene_market_party_vault_history import cli as scene_market_party_vault_history_cli
        return scene_market_party_vault_history_cli(rest)
    if cmd == "scene-push":
        from skeleton.game.gameplay.scene_tile_push import cli as scene_tile_push_cli
        return scene_tile_push_cli(rest)
    if cmd == "scene-push-play":
        from skeleton.game.gameplay.scene_tile_push_interactive import cli as scene_tile_push_interactive_cli
        return scene_tile_push_interactive_cli(rest)
    if cmd == "scene-push-accept":
        from skeleton.game.gameplay.scene_tile_push_acceptance import cli as scene_tile_push_acceptance_cli
        return scene_tile_push_acceptance_cli(rest)
    if cmd == "scene-tiles":
        from skeleton.game.gameplay.scene_tile_walk import cli as scene_tiles_cli
        return scene_tiles_cli(rest)
    if cmd == "scene-travel":
        from skeleton.game.gameplay.scene_travel import cli as scene_cli
        return scene_cli(rest)
    if cmd == "scene-npc":
        from skeleton.game.gameplay.scene_npc_encounter import cli as npc_cli
        return npc_cli(rest)
    if cmd == "scene-npc-solve":
        from skeleton.game.gameplay.scene_npc_solver import cli as npc_solver_cli
        return npc_solver_cli(rest)
    if cmd == "scene-npc-play":
        from skeleton.game.gameplay.scene_npc_interactive import cli as npc_play_cli
        return npc_play_cli(rest)
    if cmd == "game":
        from skeleton.forge.game_builder import cli as game_cli
        return game_cli(rest)
    if cmd == "forge":
        from skeleton.forge.universal import Forge
        forge = Forge(); print("Forge ready.")
        if rest:
            bp = forge.new_blueprint(rest[0])
            print(f"Blueprint '{rest[0]}' created with {len(bp.components)} components.")
        return 0
    if cmd == "test": return _cmd_test(rest)
    if cmd == "dev":
        from skeleton.developer.cli import main as developer_main
        return developer_main(rest)
    if cmd == "eras": return _cmd_eras(rest)
    if cmd == "generations": return _cmd_generations(rest)
    if cmd == "plan": return _cmd_plan(rest)
    if cmd == "cockpit": return _cmd_cockpit(rest)
    if cmd == "walk": return _cmd_walk(rest)
    if cmd == "doctor": return _cmd_doctor(rest)
    if cmd == "creator": return _cmd_creator(rest)
    if cmd == "contracts": return _cmd_contracts(rest)
    if cmd == "capabilities": return _cmd_capabilities(rest)
    if cmd == "invoke": return _cmd_invoke(rest)
    if cmd == "command": return _cmd_shared_command(rest)
    if cmd == "status": return _cmd_shared_command(["status"])
    if cmd == "config": return _cmd_shared_command(["configuration"])
    if cmd in ("help", "-h", "--help"): print(__doc__); return 0
    if cmd == "combat":
        from skeleton.game.gameplay.turn_combat import cli as combat_cli
        return combat_cli(rest)
    if cmd == "combat-contract":
        from skeleton.game.gameplay.combat_contract import cli as contract_cli
        return contract_cli(rest)
    if cmd == "combat-contract-author":
        from skeleton.game.gameplay.combat_contract_author import cli as contract_author_cli
        return contract_author_cli(rest)
    if cmd == "combat-contract-play":
        from skeleton.game.gameplay.combat_contract_interactive import cli as contract_play_cli
        return contract_play_cli(rest)
    if cmd == "combat-contract-solve":
        from skeleton.game.gameplay.combat_contract_solver import cli as contract_solver_cli
        return contract_solver_cli(rest)
    if cmd == "combat-delivery-accept":
        from skeleton.game.gameplay.combat_delivery_acceptance import cli as combat_delivery_cli
        return combat_delivery_cli(rest)
    if cmd == "combat-contract-package":
        from skeleton.game.gameplay.combat_contract_package import cli as contract_package_cli
        return contract_package_cli(rest)
    if cmd == "arena-terrain":
        from skeleton.game.gameplay.arena_terrain import cli as terrain_cli
        return terrain_cli(rest)
    if cmd == "combat-arena":
        from skeleton.game.gameplay.tactical_arena import cli as arena_cli
        return arena_cli(rest)
    if cmd == "quest-factions-accept":
        from skeleton.game.gameplay.quest_factions_acceptance import cli as faction_accept_cli
        return faction_accept_cli(rest)
    if cmd == "quest-factions-play":
        from skeleton.game.gameplay.quest_factions_interactive import cli as faction_play_cli
        return faction_play_cli(rest)
    if cmd == "quest-factions-author":
        from skeleton.game.gameplay.quest_factions_author import cli as faction_author_cli
        return faction_author_cli(rest)
    if cmd == "quest-factions-route":
        from skeleton.game.gameplay.quest_factions_route import cli as faction_route_cli
        return faction_route_cli(rest)
    if cmd == "quest-factions":
        from skeleton.game.gameplay.quest_factions import cli as faction_cli
        return faction_cli(rest)
    if cmd == "quest-author":
        from skeleton.game.gameplay.expedition_quest_author import cli as author_cli
        return author_cli(rest)
    if cmd == "quest-expedition":
        from skeleton.game.gameplay.expedition_quest import cli as quest_cli
        return quest_cli(rest)
    if cmd == "quest-expedition-play":
        from skeleton.game.gameplay.expedition_quest_interactive import cli as quest_play_cli
        return quest_play_cli(rest)
    if cmd == "quest-inventory":
        from skeleton.game.gameplay.expedition_quest_inventory import cli as quest_inventory_cli
        return quest_inventory_cli(rest)
    if cmd == "quest-decisions":
        from skeleton.game.gameplay.expedition_quest_decisions import cli as quest_decision_cli
        return quest_decision_cli(rest)
    if cmd == "quest-checkpoints":
        from skeleton.game.gameplay.expedition_quest_checkpoints import cli as quest_checkpoint_cli
        return quest_checkpoint_cli(rest)
    if cmd == "quest-expedition-route":
        from skeleton.game.gameplay.expedition_quest_route import cli as quest_route_cli
        return quest_route_cli(rest)
    if cmd == "quest-campaign-play":
        from skeleton.game.gameplay.quest_chapter_campaign_interactive import cli as campaign_play_cli
        return campaign_play_cli(rest)
    if cmd == "quest-campaign-accept":
        from skeleton.game.gameplay.quest_chapter_campaign_accept import cli as campaign_accept_cli
        return campaign_accept_cli(rest)
    if cmd == "quest-campaign-route":
        from skeleton.game.gameplay.quest_chapter_campaign_route import cli as campaign_route_cli
        return campaign_route_cli(rest)
    if cmd == "game-vertical-accept":
        from skeleton.game.gameplay.game_vertical_acceptance import cli as vertical_accept_cli
        return vertical_accept_cli(rest)
    if cmd == "quest-campaign":
        from skeleton.game.gameplay.quest_chapter_campaign import cli as campaign_cli
        return campaign_cli(rest)
    if cmd == "quest-campaign-author":
        from skeleton.game.gameplay.quest_chapter_campaign_author import cli as campaign_author_cli
        return campaign_author_cli(rest)
    if cmd == "arena-forge-author":
        from skeleton.game.gameplay.arena_forge_author import cli as forge_author_cli
        return forge_author_cli(rest)
    if cmd == "arena-forge-solve":
        from skeleton.game.gameplay.arena_forge_solver import cli as forge_solver_cli
        return forge_solver_cli(rest)
    if cmd == "arena-forge":
        from skeleton.game.gameplay.arena_forge_run import cli as forge_cli
        return forge_cli(rest)
    if cmd == "combat-checkpoints":
        from skeleton.game.gameplay.arena_checkpoint_timeline import cli as checkpoint_cli
        return checkpoint_cli(rest)
    if cmd == "combat-expedition-playbook":
        from skeleton.game.gameplay.arena_expedition_playbook import cli as playbook_cli
        return playbook_cli(rest)
    if cmd == "combat-expedition-audit":
        from skeleton.game.gameplay.arena_expedition_economy import cli as expedition_audit_cli
        return expedition_audit_cli(rest)
    if cmd == "combat-expedition-solve":
        from skeleton.game.gameplay.arena_expedition_solver import cli as expedition_solver_cli
        return expedition_solver_cli(rest)
    if cmd == "combat-expedition":
        from skeleton.game.gameplay.arena_expedition import cli as expedition_cli
        return expedition_cli(rest)
    if cmd == "tournament-author":
        from skeleton.game.gameplay.combat_tournament_author import cli as author_cli
        return author_cli(rest)
    if cmd == "combat-league-author":
        from skeleton.game.gameplay.combat_league_author import cli as league_author_cli
        return league_author_cli(rest)
    if cmd == "combat-career-roadmap":
        from skeleton.game.gameplay.combat_league_career_roadmap import cli as roadmap_cli
        return roadmap_cli(rest)
    if cmd == "combat-career-advice":
        from skeleton.game.gameplay.combat_league_career_advice import cli as career_advice_cli
        return career_advice_cli(rest)
    if cmd == "combat-career-author":
        from skeleton.game.gameplay.combat_league_career_author import cli as career_author_cli
        return career_author_cli(rest)
    if cmd == "combat-career":
        from skeleton.game.gameplay.combat_league_career import cli as career_cli
        return career_cli(rest)
    if cmd == "combat-league":
        from skeleton.game.gameplay.combat_league import cli as league_cli
        return league_cli(rest)
    if cmd == "combat-tournament":
        from skeleton.game.gameplay.combat_tournament import cli as tournament_cli
        return tournament_cli(rest)
    if cmd == "combat-campaign-timeline":
        from skeleton.game.gameplay.combat_campaign_timeline import cli as campaign_timeline_cli
        return campaign_timeline_cli(rest)
    if cmd == "combat-campaign-player":
        from skeleton.game.gameplay.combat_campaign_player import cli as campaign_player_cli
        return campaign_player_cli(rest)
    if cmd == "combat-campaign":
        from skeleton.game.gameplay.combat_campaign import cli as campaign_cli
        return campaign_cli(rest)
    if cmd == "combat-balance":
        from skeleton.game.gameplay.combat_balance import cli as balance_cli
        return balance_cli(rest)
    if cmd == "combat-drill-solve":
        from skeleton.game.gameplay.combat_drill_solver import cli as drill_solver_cli
        return drill_solver_cli(rest)
    if cmd == "combat-stamina":
        from skeleton.game.gameplay.combat_stamina import cli as stamina_cli
        return stamina_cli(rest)
    if cmd == "combat-drill":
        from skeleton.game.gameplay.combat_drill import cli as drill_cli
        return drill_cli(rest)
    if cmd == "combat-inspect":
        from skeleton.game.gameplay.combat_inspector import cli as inspect_cli
        return inspect_cli(rest)
    if cmd == "campaign":
        from scripts.game.offline_grid_campaign import main as campaign_cli
        return campaign_cli(rest)
    if cmd == "world-laptop":
        from skeleton.jeeves.worlds.laptop_cli import run as world_laptop_cli
        return world_laptop_cli(rest)
    if cmd == "world-canon":
        from skeleton.jeeves.worlds.cli import run as world_canon_cli
        return world_canon_cli(rest)
    if cmd == "world-assets":
        from skeleton.jeeves.worlds.assets_cli import run as world_assets_cli
        return world_assets_cli(rest)
    if cmd == "world-timeline":
        from skeleton.jeeves.worlds.timeline_cli import run as world_timeline_cli
        return world_timeline_cli(rest)
    if cmd == "world-bundle":
        from skeleton.jeeves.worlds.bundle_cli import run as world_bundle_cli
        return world_bundle_cli(rest)
    if cmd == "world-plan":
        from skeleton.jeeves.worlds.plan_cli import run as world_plan_cli
        return world_plan_cli(rest)
    if cmd == "world-editor":
        from skeleton.jeeves.worlds.editor_cli import run as world_editor_cli
        return world_editor_cli(rest)
    if cmd == "world-route":
        from skeleton.jeeves.worlds.route_cli import run as world_route_cli
        return world_route_cli(rest)
    if cmd == "world-cast":
        from skeleton.jeeves.worlds.cast_cli import run as world_cast_cli
        return world_cast_cli(rest)
    if cmd == "world-experience":
        from skeleton.jeeves.worlds.experience_cli import run as world_experience_cli
        return world_experience_cli(rest)
    if cmd == "world-revision":
        from skeleton.jeeves.worlds.revision_cli import run as world_revision_cli
        return world_revision_cli(rest)
    if cmd == "world-assurance":
        from skeleton.jeeves.worlds.assurance_cli import run
        return run(rest)
    if cmd == "world-invariants":
        from skeleton.jeeves.worlds.invariants_cli import run
        return run(rest)
    if cmd == "world-scenario":
        from skeleton.jeeves.worlds.scenario_cli import run
        return run(rest)
    if cmd == "world-choice-impact":
        from skeleton.jeeves.worlds.choice_impact_cli import run
        return run(rest)
    if cmd == "world-playtest":
        from skeleton.jeeves.worlds.playtest_cli import run as world_playtest_cli
        return world_playtest_cli(rest)
    if cmd == "world-migrate":
        from skeleton.jeeves.worlds.migration_cli import run
        return run(rest)
    if cmd == "world-field-journal":
        from skeleton.jeeves.worlds.field_journal_cli import run as field_journal_cli
        return field_journal_cli(rest)
    if cmd == "world-weather":
        from skeleton.jeeves.worlds.weather_cli import run as world_weather_cli
        return world_weather_cli(rest)
    if cmd == "world-advisories":
        from skeleton.jeeves.worlds.advisories_cli import run as advisories_cli
        return advisories_cli(rest)
    if cmd == "world-epilogues":
        from skeleton.jeeves.worlds.epilogues_cli import run as epilogues_cli
        return epilogues_cli(rest)
    if cmd == "world-fork":
        from skeleton.jeeves.worlds.branching_cli import run as world_fork_cli
        return world_fork_cli(rest)
    if cmd == "world-session":
        from skeleton.jeeves.worlds.session_cli import run as world_session_cli
        return world_session_cli(rest)
    if cmd == "world-quest":
        from skeleton.jeeves.worlds.quest_cli import run as world_quest_cli
        return world_quest_cli(rest)
    if cmd == "world-counterfactual":
        from skeleton.jeeves.worlds.counterfactual_cli import run as world_counterfactual_cli
        return world_counterfactual_cli(rest)
    if cmd == "world-lore":
        from skeleton.jeeves.worlds.lore_cli import run as world_lore_cli
        return world_lore_cli(rest)
    if cmd == "world-factions":
        from skeleton.jeeves.worlds.factions_cli import run as world_factions_cli
        return world_factions_cli(rest)
    if cmd == "world-evidence":
        from skeleton.jeeves.worlds.evidence_cli import run as world_evidence_cli
        return world_evidence_cli(rest)
    if cmd == "world-integrated":
        from skeleton.jeeves.worlds.integrated_cli import run as world_integrated_cli
        return world_integrated_cli(rest)
    if cmd == "world-context":
        from skeleton.jeeves.worlds.context_cli import run as world_context_cli
        return world_context_cli(rest)
    if cmd == "world-promises":
        from skeleton.jeeves.worlds.promises_cli import run as world_promises_cli
        return world_promises_cli(rest)
    if cmd == "world-knowledge":
        from skeleton.jeeves.worlds.knowledge_cli import run as world_knowledge_cli
        return world_knowledge_cli(rest)
    if cmd == "world-studio-engine":
        from skeleton.jeeves.worlds.studio_engine_cli import run as world_studio_engine_cli
        return world_studio_engine_cli(rest)
    if cmd == "world-studio":
        from skeleton.jeeves.worlds.studio_assembly_cli import run as world_studio_cli
        return world_studio_cli(rest)
    if cmd == "world-director":
        from skeleton.jeeves.worlds.director_cli import run as world_director_cli
        return world_director_cli(rest)
    if cmd == "world-chapters":
        from skeleton.jeeves.worlds.chapters_cli import run as world_chapters_cli
        return world_chapters_cli(rest)
    if cmd == "world-cinematics":
        from skeleton.jeeves.worlds.cinematics_cli import run as world_cinematics_cli
        return world_cinematics_cli(rest)
    if cmd == "world-pacing":
        from skeleton.jeeves.worlds.pacing_cli import run as world_pacing_cli
        return world_pacing_cli(rest)
    if cmd == "world-accessibility":
        from skeleton.jeeves.worlds.accessibility_cli import run as world_accessibility_cli
        return world_accessibility_cli(rest)
    if cmd == "world-localization":
        from skeleton.jeeves.worlds.localization_cli import run as world_localization_cli
        return world_localization_cli(rest)
    if cmd == "world-rumors":
        from skeleton.jeeves.worlds.rumors_cli import run as world_rumors_cli
        return world_rumors_cli(rest)
    if cmd == "world-testimony":
        from skeleton.jeeves.worlds.testimony_cli import run as world_testimony_cli
        return world_testimony_cli(rest)
    if cmd == "world-relationships":
        from skeleton.jeeves.worlds.relationships_cli import run as relationships_cli
        return relationships_cli(rest)
    if cmd == "world-events":
        from skeleton.jeeves.worlds.events_cli import run as world_events_cli
        return world_events_cli(rest)
    if cmd == "world-puzzles":
        from skeleton.jeeves.worlds.puzzles_cli import run as world_puzzles_cli
        return world_puzzles_cli(rest)
    if cmd == "world-inventory":
        from skeleton.jeeves.worlds.inventory_cli import run as world_inventory_cli
        return world_inventory_cli(rest)
    if cmd == "world-npc-schedule":
        from skeleton.jeeves.worlds.npc_schedule_cli import run as npc_schedule_cli
        return npc_schedule_cli(rest)
    if cmd == "world-portals":
        from skeleton.jeeves.worlds.portals_cli import run as world_portals_cli
        return world_portals_cli(rest)
    if cmd == "world-atlas":
        from skeleton.jeeves.worlds.atlas_cli import run as world_atlas_cli
        return world_atlas_cli(rest)
    if cmd == "world-dialogue-locales":
        from skeleton.jeeves.worlds.dialogue_localization_cli import run as dialogue_locales_cli
        return dialogue_locales_cli(rest)
    if cmd == "world-dialogue-transcript":
        from skeleton.jeeves.worlds.dialogue_transcript_cli import run as transcript_cli
        return transcript_cli(rest)
    if cmd == "world-interaction":
        from skeleton.jeeves.worlds.interaction_assembly_cli import run as interaction_cli
        return interaction_cli(rest)
    if cmd == "world-dialogue":
        from skeleton.jeeves.worlds.dialogue_graph_cli import run as dialogue_cli
        return dialogue_cli(rest)
    if cmd == "world-character-arcs":
        from skeleton.jeeves.worlds.character_arcs_cli import run as arcs_cli
        return arcs_cli(rest)
    if cmd == "world-economy":
        from skeleton.jeeves.worlds.economy_cli import run as economy_cli
        return economy_cli(rest)
    if cmd == "world-tools":
        from skeleton.jeeves.worlds.tools_cli import run as world_tools_cli
        return world_tools_cli(rest)
    if cmd == "quest":
        from skeleton.game.gameplay.quest_cli import main as quest_main
        return quest_main(rest)
    print(f"Unknown command: {cmd}"); print(__doc__); return 1


if __name__ == "__main__":
    raise SystemExit(main())
