# Skeleton Frontier Consolidation

**Program:** Frontier Model Build  
**Lead:** Apeloff1  
**Canonical repository:** `Apeloff1/Skeleton`  
**Branch:** `frontier/consolidation-foundation`

## Mission

Consolidate the strongest AI, learning, agent, game, world, and cockpit capabilities from the Apeloff1 repository family into one coherent platform. The objective is not to concatenate repositories; it is to produce a production-grade AI operating substrate with explicit contracts, replaceable implementations, and a polished developer/operator surface.

## Non-negotiables

1. Skeleton is the canonical root.
2. Preserve useful implementation provenance in `docs/lineage/` and consolidation manifests.
3. Never merge secrets, generated caches, dependency directories, or opaque build output into normal Git history.
4. Large model/data/game assets use Git LFS or external artifact storage.
5. Every promoted subsystem receives a contract, tests, observability, and security boundary.
6. No duplicate “core” implementations: one canonical interface, multiple adapters where justified.
7. Existing working behavior is preferred over speculative rewrites.
8. Experimental code may remain quarantined until it passes promotion gates.

## Target architecture

```text
core/kernel
    -> runtime
    -> memory
    -> intelligence
    -> swarm
    -> game
    -> learning
    -> forge
    -> services
    -> cockpit
```

### Core planes

- **Kernel:** events, errors, clocks, registries, invariants.
- **Runtime:** lifecycle, configuration, execution context, capabilities.
- **Memory:** RAG/CAG/MAG, vector retrieval, provenance, memory policies.
- **Intelligence:** agents, orchestration, planning, reasoning, evaluation, tool use.
- **Swarm:** multi-agent routing, coordination, work queues, collective state.
- **Game:** worlds, NPCs, dialogue, quests, simulation, mechanics, animation.
- **Learning:** tutoring, curriculum, ZPD, mastery, gamification, knowledge packs.
- **Forge:** blueprints, generators, materialization, project scaffolding.
- **Services:** API, persistence, auth, jobs, storage, telemetry.
- **Cockpit:** operator UI, dashboards, inspectors, visualization, command center.

## Promotion gates

A component moves from source repository to canonical implementation only after:

- source provenance recorded;
- dependencies mapped;
- public API identified;
- secrets/config audit completed;
- unit tests or characterization tests added;
- integration boundary defined;
- duplicate implementations compared;
- performance implications documented;
- security capabilities declared;
- owner/maintainer identified.

## Workstreams

### W0 — Control plane
Branching, CI, repository inventory, architecture records, dependency policy, security scanning.

### W1 — Kernel/runtime
Stabilize boot, event bus, registry, config, runtime context, capability model.

### W2 — Intelligence
Unify agent lifecycle, orchestration, tool invocation, planning, reasoning, evaluation.

### W3 — Memory
Unify retrieval, memory planes, vector adapters, provenance, ranking and fusion.

### W4 — Learning/Jeeves
Promote tutoring, system laws, learning matrices, co-coding and knowledge packs as adapters on the common intelligence/memory substrate.

### W5 — Game/world
Promote NPC, dialogue, quest, world and simulation implementations from Lorebuffa/Openworld/GameForge families.

### W6 — Forge
Unify blueprint generation and materialization; expose one project-generation contract.

### W7 — Cockpit
Integrate HyperForge's web stack as the operator/developer surface without coupling UI concerns into the kernel.

### W8 — Validation
Unit, integration, E2E, load, chaos, benchmark, security, reproducibility.

### W9 — Asset/artifact plane
Move large assets into explicit LFS/artifact boundaries and document reproducible acquisition/build procedures.

## Definition of done

The frontier build is considered consolidated when:

- one command boots the platform;
- one CLI discovers and operates all major subsystems;
- one agent contract powers Jeeves and game agents;
- one memory contract powers learning and game retrieval;
- one event/telemetry model crosses subsystem boundaries;
- cockpit can inspect runtime, agents, memory, worlds, jobs and health;
- all promoted modules have tests and documented failure modes;
- source repository remains maintainable while total platform assets can scale to the requested multi-GB footprint through proper artifact channels.
