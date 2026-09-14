# Galaxy Studio / Jeeves Benchmark — Game Creation + AI Agent Systems

Date: 2026-09-14

This benchmark is not a feature checklist for cloning competitors. It identifies
repeated structural advantages across major game-creation and AI-agent systems,
then turns them into native Galaxy Studio primitives. The target is a system
that can absorb future tools without reorganizing around each vendor.

## Executive conclusion

The strongest game-creation systems converge on a small number of ideas:

1. a canonical project/world model that both tools and runtime can manipulate;
2. reusable compositional units (scenes, prefabs, packages, blueprints, assets);
3. visual editing and code that operate on the same state rather than parallel copies;
4. immediate preview/playtest loops;
5. scalable world/runtime partitioning and explicit networking authority;
6. extensible procedural tooling;
7. durable versioned assets and collaborative workflows.

The strongest AI coding/agent systems converge on a parallel set:

1. isolated execution environments/worktrees;
2. durable sessions that can be monitored, steered, stopped and resumed;
3. specialized agents with scoped tools/capabilities;
4. parallel subagent execution where isolation is beneficial;
5. explicit permission/sandbox boundaries;
6. persistent project knowledge and reusable skills/playbooks;
7. observable tool activity, diffs, tests and review handoffs;
8. long-horizon state tracked outside a single model context window.

Galaxy Studio should unify both families. A game-edit operation and an AI tool
operation should ultimately be transactions against typed project state, executed
through the same bounded capability runtime, with evidence and rollback.

## Game creation benchmark

| System | Structural strength worth promoting | Galaxy Studio response |
| --- | --- | --- |
| Unreal Engine | Modular Gameplay Framework; World Partition keeps a large world in a single persistent level while streaming grid cells; PCG integrates procedural generation with World Partition/data layers. | Canonical `WorldGraph`; partition/stream metadata as graph policy; procedural generators emit transactions rather than opaque files. |
| Unity 6 | ECS/Entities for data-oriented composition, Visual Scripting for graph-based behavior, and integrated multiplayer packages. | Components become typed data contracts; behaviors can be represented as graph IR and code; simulation/network authority is explicit metadata. |
| Godot | Games are trees of nodes grouped into reusable/nestable scenes; signals decouple communication; scripts extend the same nodes the editor manipulates. | Scene/prefab composition is native to `WorldGraph`; event/signal edges are first-class; code and visual tools mutate the same node identities. |
| Roblox Studio | A flexible data model is editable at design time and runtime; packages provide reusable/versioned objects; Studio Assistant can modify the data model and scripts; collaboration and publishing are integrated. | Jeeves receives typed world-edit capabilities instead of text-only generation; reusable constructs carry version lineage; AI actions generate reviewable world diffs. |
| GameMaker | Object/event/room/sequence model optimizes for low-friction authoring and direct event-driven behavior. | Preserve a fast authoring layer above the general graph: objects + event bindings should be ergonomic projections, not a separate engine. |
| GDevelop / Construct-class event engines | Event sheets/behaviors make logic composable for non-programmers and keep iteration fast. | Provide declarative behavior graphs compiled to the same runtime IR as authored code; no second-class 'no-code' project format. |
| Blender | Geometry Nodes turns node groups into reusable tools/assets; asset libraries make procedural authoring distributable. | Procedural graph definitions are packageable capabilities that can be versioned, shared and invoked by humans or Jeeves. |

### Primary game-system lessons

**One world, many projections.** Unreal World Partition, Godot scenes, Roblox's
data model and Unity ECS all reinforce the same decision: Galaxy Studio needs a
canonical world/project graph. Files, panels, AI prompts and visual editors should
be projections of that graph, not competing sources of truth.

**Reusable units require lineage.** Godot scenes and Roblox packages make nested
reuse normal. Galaxy constructs should therefore carry stable identity, source
version, overrides, update policy and rollback metadata.

**AI must manipulate the actual project model.** Roblox Assistant can operate on
the Studio data model, which is materially stronger than an assistant that only
returns snippets. Jeeves capabilities should apply typed transactions and return
structured diffs/evidence.

**Procedural generation is an editor/runtime primitive.** Unreal PCG and Blender
Geometry Nodes both treat procedural graphs as reusable tools. Galaxy procedural
systems should emit deterministic graph transactions with seeds, inputs and
provenance so outputs can be regenerated or selectively adopted.

## AI agent benchmark

| System | Structural strength worth promoting | Jeeves response |
| --- | --- | --- |
| OpenAI Codex / Agents API | Parallel agents, worktrees/cloud environments, hosted sandboxes, long-running sessions, skills and tool use. | Bounded `JeevesRuntime`, isolated workspaces, durable `JeevesRun`, capability registry, reusable skills, parallel work only behind explicit budgets. |
| GitHub Copilot agents | Custom agents have scoped prompts/tools/MCP; subagents run isolated contexts; cloud sessions are monitorable and review via PRs. | Agent identity becomes a capability profile rather than authority; every delegated run has its own scope, evidence and merge/adoption gate. |
| Anthropic agentic guidance / Claude | Long-horizon state tracking, external progress/test state, parallel tool use, specialized subagents and verification loops. | Persist run state outside model context; checkpoint before compaction/handoff; keep structured tests/evidence; delegate only separable workstreams. |
| Cursor Background Agents | Isolated remote machines, separate branches, environment snapshots, terminal execution and takeover/follow-up. | Workspace/sandbox profiles are versioned inputs; environment boot is reproducible; users can cancel/take over without losing evidence. |
| Devin | IDE + shell + browser in one observable session, persistent Knowledge, reusable playbooks and parallel managed sessions. | `JeevesRun` has multi-tool event history; `JeevesMemory` retrieves durable project lessons; playbooks become versioned workflow graphs. |

### Primary agent-system lessons

**Agent count is not capability.** Skeleton's procedural million-agent mesh is useful
as an addressing/delegation topology, but it must not be treated as proof of
execution capacity. Real capacity is defined by bounded queues, sandbox resources,
tool permissions, model budget and measurable throughput.

**Specialization must be enforced mechanically.** A named 'security agent' is weak
unless its tools, data access, mutation rights, budget and output contract are
scoped. `CapabilityRegistry` is therefore more important than persona count.

**Durability belongs outside the context window.** Long tasks need persisted plan
state, checkpoints, evidence, memory and workspace state. A model context is a
working set, not the system of record.

**Mutation needs a higher bar than ordinary evolution.** Agent systems are good at
generating alternatives; they are not automatically good judges of whether a
working architecture should be replaced. Galaxy's `EvolutionPolicy` therefore
requires measured improvement, protected metrics and explicit rollback for broad
mutation.

## Target architecture

### 1. WorldGraph — canonical project state

A stable identity graph containing:

- world/scene nodes;
- components and behavior bindings;
- asset/package references;
- signals/event edges;
- simulation/network authority;
- partition/streaming metadata;
- editor-only metadata;
- provenance and version lineage.

All edits are atomic `WorldPatch` transactions with preconditions. A patch returns
a diff and inverse/rollback representation. The visual editor, code editor,
procedural generators and Jeeves use the same transaction API.

### 2. ForgeComponent / Package — reusable composition

Reusable constructs must carry:

- immutable package version identity;
- nested dependencies;
- exposed parameters;
- instance overrides;
- update policy (pinned/manual/auto);
- migration hooks;
- source provenance;
- compatibility contract.

This combines the practical value of prefabs/scenes/packages without copying any
one engine's file model.

### 3. BehaviorGraph — visual/code parity

Behavior is represented as typed intermediate representation:

- events/signals;
- conditions;
- state transitions;
- actions/capability calls;
- data flow;
- deterministic scheduling metadata.

Visual editing and authored code both compile/translate to this IR. The project
never has separate 'real logic' and 'visual logic' universes.

### 4. LiveSession — preview, simulation, rollback

A live authoring session owns:

- base world revision;
- ephemeral transaction overlay;
- deterministic simulation seed;
- hot-reloadable behavior/component revisions;
- captured metrics and traces;
- accept/discard/merge outcome.

AI-generated changes should normally enter a LiveSession first, not mutate the
canonical project directly.

### 5. JeevesRuntime — bounded control plane

Already started on this branch:

- priority admission;
- bounded queueing;
- cooperative cancellation;
- wall-clock and step budgets;
- progressive degradation/governor;
- capability contracts;
- approval-gated mutations;
- structured execution evidence.

This is the shared runtime for code agents and game-building agents.

### 6. JeevesRun — durable long-horizon execution

A durable run should persist:

- directive + resolved plan graph;
- workspace/sandbox identity;
- capability snapshot;
- model/provider decisions;
- checkpoints;
- tool calls/results;
- world/code diffs;
- tests/benchmarks;
- evidence hashes;
- cancellation/replan history;
- adoption decision.

Restarting a worker must not destroy run state.

### 7. JeevesMemory — bounded episodic + reflective knowledge

Promoted from the useful private Prood idea but redesigned provider-neutral:

- episodic records;
- importance + recency + query relevance;
- explicit reflection records;
- reflection source lineage;
- bounded per-agent capacity;
- persistence adapter outside the core primitive.

Memories influence future planning only as retrieved evidence/context; they do not
silently grant authority.

### 8. EvolutionPolicy — evidence-gated self-improvement

Default path:

`baseline -> candidate -> isolated simulation/test -> metric comparison -> adopt/reject`

Broad mutation additionally requires:

- stronger minimum measured gain;
- rollback reference;
- protected-metric tolerances;
- sufficient independent evidence.

This turns 'evolve' from a slogan into an enforceable merge/adoption contract.

### 9. ModelRouter — provider-neutral intelligence policy

Provider selection should be based on declared needs rather than hard-coded brand
names:

- task type;
- required tools/modalities;
- context size;
- latency budget;
- cost budget;
- reliability history;
- privacy/sandbox constraints;
- measured model performance for this workload.

Fallback is policy-driven and observable. Silent provider substitution is not.

### 10. EvidenceEnvelope — every meaningful action is inspectable

Every run/transaction should be able to emit:

- inputs and resolved identities;
- capability/tool used;
- changed objects/files;
- stdout/stderr or structured tool result;
- tests/benchmarks;
- model/provider metadata where applicable;
- provenance head/hash;
- adoption/approval decision.

Evidence is what allows Jeeves to become more autonomous without becoming less
accountable.

## Positioning against current tools

Galaxy Studio should not try to beat Unreal at renderer maturity, Blender at DCC
breadth, Roblox at installed creator ecosystem, or a frontier coding agent at raw
model quality in isolation. Its defensible position is the **unification layer**:

- one mutable graph spanning game state, assets, behavior and generated output;
- one bounded execution substrate for human tools and AI tools;
- one evidence/provenance model;
- one evolution/adoption policy;
- provider-neutral intelligence;
- reusable workflows that can target multiple runtimes/exporters.

That makes external engines, models and tools potential backends/capabilities rather
than architectural competitors that require rebuilding the product around them.

## Implementation order

1. Land and validate `JeevesRuntime` integration.
2. Land `JeevesMemory` and `EvolutionPolicy` with tests.
3. Implement transactional `WorldGraph` + inverse patches.
4. Move existing generated gamefiles toward graph-backed constructs.
5. Add `LiveSession` overlays and simulation/adoption evidence.
6. Wrap existing generator/gate/churn functions as typed capabilities.
7. Add provider-neutral `ModelRouter` telemetry and explicit fallback policy.
8. Persist `JeevesRun` state so worker restarts are survivable.
9. Add package/prefab lineage and update policy.
10. Expose one UI that shows project graph, agent runs, diffs, evidence and adoption.

## Sources reviewed

- Epic Unreal Gameplay Framework: https://dev.epicgames.com/documentation/unreal-engine/gameplay-framework-in-unreal-engine
- Epic World Partition: https://dev.epicgames.com/documentation/unreal-engine/world-partition-in-unreal-engine
- Epic PCG: https://dev.epicgames.com/documentation/unreal-engine/pcg-development-guides
- Unity Entities: https://docs.unity3d.com/6000.0/Documentation/Manual/com.unity.entities.html
- Unity Visual Scripting: https://docs.unity3d.com/6000.0/Documentation/Manual/com.unity.visualscripting.html
- Roblox Studio: https://create.roblox.com/docs/studio
- Roblox Packages: https://create.roblox.com/docs/projects/assets/packages
- Roblox AI workflows/MCP: https://create.roblox.com/docs/ai/accelerated-workflows
- Godot key concepts: https://docs.godotengine.org/en/stable/getting_started/introduction/key_concepts_overview.html
- Blender Geometry Node tools: https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/tools.html
- OpenAI Agents API: https://openai.com/index/introducing-the-agents-api/
- OpenAI Codex: https://openai.com/codex/
- OpenAI agent security controls: https://openai.com/index/running-codex-safely/
- GitHub Copilot custom agents/subagents: https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/custom-agents
- GitHub Copilot agent sessions: https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/overview
- Anthropic agentic prompting guidance: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables
- Cursor Background Agents: https://docs.cursor.com/background-agent
- Devin overview/session tools/knowledge: https://docs.devin.ai/get-started/devin-intro ; https://docs.devin.ai/work-with-devin/devin-session-tools ; https://docs.devin.ai/product-guides/knowledge
