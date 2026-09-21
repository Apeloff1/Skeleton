# Skeleton AI Edge Cases, Obscure Patterns & Historical Architecture Catalogue

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Machine mirror: [`machine/ai_edge_case_catalog.json`](../../machine/ai_edge_case_catalog.json)

Master index: [`MASTER_INDEX.md`](MASTER_INDEX.md)

## Purpose

This catalogue is the anti-amnesia layer for the breadth-frozen master plan. It captures failure modes that are easy to miss in happy-path architecture, obscure systems lessons that are routinely rediscovered, and historical AI/software designs whose strengths and failures should inform Skeleton.

The catalogue **does not create new top-level volumes**. Every entry maps back to one or more existing Volume 000–420 domains.

## Operating rules

- Historical systems are studied for mechanisms and failure lessons, not copied wholesale.
- An edge case should become a regression test, property, invariant, chaos scenario, runbook, or explicit accepted risk when its mapped capability is implemented.
- “Obscure” means easy to overlook, not optional.
- Duplicate-looking failures should remain separate when their recovery semantics differ.
- Model-generated confidence is never evidence that an edge case is handled.
- Unknown/ambiguous external outcomes must remain explicit.
- Platform-specific behavior must be tested on the affected platform rather than assumed from POSIX-only behavior.
- Any P0 capability that crosses network, process, tool, storage, model, or user boundaries should consult this catalogue during acceptance design.

## Coverage summary

- Historical AI/system patterns: **70**
- Concrete edge/failure cases: **140**
- Obscure cross-cutting lessons: **30**
- Total catalogue entries: **240**

## Historical AI and systems lineage

| ID | Pattern / system | Domain | Mapped volumes | Skeleton lesson |
| --- | --- | --- | --- | --- |
| `HIST-AI-001` | General Problem Solver | reasoning/planning | VOL-001, VOL-013, VOL-014, VOL-313 | Early means-ends analysis showed the value—and brittleness—of explicit problem reduction. |
| `HIST-AI-002` | STRIPS planning | planning | VOL-001, VOL-014, VOL-370, VOL-372 | Preconditions/effects remain useful for tool plans, static analysis, rollback and simulation. |
| `HIST-AI-003` | SHRDLU | grounded cognition | VOL-001, VOL-019, VOL-249 | Grounded language in a constrained world demonstrated the power of explicit world state and the danger of narrow-domain competence being mistaken for generality. |
| `HIST-AI-004` | DENDRAL | expert systems | VOL-001, VOL-071, VOL-311 | Domain knowledge plus search can outperform generic reasoning; specialist capability packs should remain first-class. |
| `HIST-AI-005` | MYCIN | expert systems | VOL-001, VOL-012, VOL-028, VOL-085 | Rule-based expert systems exposed explanation, uncertainty and knowledge-maintenance problems still relevant to policy and evidence systems. |
| `HIST-AI-006` | HEARSAY-II blackboard | blackboard systems | VOL-001, VOL-017, VOL-201 | A shared blackboard coordinating specialist modules is an ancestor of modern multi-agent/shared-state orchestration. |
| `HIST-AI-007` | Rete networks | rule engines | VOL-001, VOL-028, VOL-335 | Incremental rule matching demonstrates why derived state and incremental recomputation can outperform full rescans. |
| `HIST-AI-008` | Truth Maintenance Systems | knowledge representation | VOL-001, VOL-012, VOL-248, VOL-359 | TMS/ATMS ideas map directly to claims, contradictions, assumptions, supersession and belief revision. |
| `HIST-AI-009` | SOAR | cognitive architecture | VOL-001, VOL-013, VOL-024, VOL-366 | Production rules plus chunking illustrate both reusable learned procedures and the risk of accumulating brittle internal rules. |
| `HIST-AI-010` | ACT-R | cognitive architecture | VOL-001, VOL-010, VOL-013 | Separating declarative/procedural memory remains a useful conceptual split even when implementations are neural. |
| `HIST-AI-011` | Subsumption architecture | robotics/control | VOL-001, VOL-013, VOL-317 | Layered reactive behavior is a reminder that not every task requires deliberative planning. |
| `HIST-AI-012` | Behavior trees | agent control | VOL-001, VOL-017, VOL-073, VOL-306 | Explicit fallback/sequence semantics remain useful for agent and game workflows because they are inspectable and bounded. |
| `HIST-AI-013` | Contract Net Protocol | multi-agent | VOL-001, VOL-017, VOL-315 | Task announcement, bidding and award are historical roots for capability-aware agent scheduling. |
| `HIST-AI-014` | BDI agents | multi-agent | VOL-001, VOL-012, VOL-014, VOL-017 | Belief–desire–intention separation is useful when distinguishing world knowledge, objectives and committed plans. |
| `HIST-AI-015` | Society of Mind | multi-agent | VOL-001, VOL-017, VOL-206 | Many small specialists can be useful, but coordination overhead and emergent conflict must be explicit. |
| `HIST-AI-016` | Cyc | knowledge systems | VOL-001, VOL-012, VOL-247 | Large hand-built knowledge bases demonstrate the importance of ontology, provenance, scope and maintenance cost. |
| `HIST-AI-017` | Case-based reasoning | memory/reasoning | VOL-001, VOL-010, VOL-013 | Past solved cases are useful only when similarity, context and adaptation are handled explicitly. |
| `HIST-AI-018` | Genetic algorithms | evolutionary search | VOL-001, VOL-023, VOL-024, VOL-324 | Population search foreshadows candidate-generation/selection in Forge, but fitness functions can be gamed. |
| `HIST-AI-019` | Genetic programming | evolutionary computation | VOL-001, VOL-023, VOL-025, VOL-037 | Evolving programs highlights the need for sandboxing, complexity penalties and independent verification. |
| `HIST-AI-020` | Hopfield networks | neural memory | VOL-001, VOL-010, VOL-350 | Associative memory is a historical reminder that retrieval and memory can be content-addressable rather than key-addressed. |
| `HIST-AI-021` | Boltzmann machines | neural models | VOL-001, VOL-006, VOL-013 | Energy-based models illustrate stochastic search and the difficulty of reliable convergence. |
| `HIST-AI-022` | Reservoir computing | neural models | VOL-001, VOL-006, VOL-231 | Fixed recurrent dynamics plus trained readouts remain relevant to lightweight temporal specialists. |
| `HIST-AI-023` | LSTM/GRU | sequence models | VOL-001, VOL-006, VOL-010 | Gating solved parts of long-dependency learning but did not remove finite-memory or drift issues. |
| `HIST-AI-024` | Attention before Transformers | model history | VOL-001, VOL-006, VOL-009 | Attention's alignment roots matter when evaluating what information a model actually conditions on. |
| `HIST-AI-025` | Transformer architecture | model history | VOL-001, VOL-006, VOL-007 | Parallel attention changed scaling behavior but retained context-window, data and verification limitations. |
| `HIST-AI-026` | Mixture of Experts | model routing | VOL-001, VOL-006, VOL-008, VOL-382 | Sparse specialization motivates capability routing but introduces load-balancing and expert-collapse concerns. |
| `HIST-AI-027` | Memory Networks | memory architectures | VOL-001, VOL-010, VOL-011 | Explicit external memory anticipated modern retrieval/memory hybrids. |
| `HIST-AI-028` | Neural Turing Machine | memory architectures | VOL-001, VOL-010, VOL-013 | Differentiable external memory shows why memory interfaces and addressing strategies matter independently of the base model. |
| `HIST-AI-029` | Differentiable Neural Computer | memory architectures | VOL-001, VOL-010, VOL-012 | Memory allocation/linkage mechanisms foreshadow explicit structured memory graphs. |
| `HIST-AI-030` | Information retrieval lineage | retrieval | VOL-001, VOL-011, VOL-035 | Boolean retrieval, TF-IDF, vector-space models and BM25 remain strong baselines against dense retrieval. |
| `HIST-AI-031` | Latent Semantic Analysis | retrieval | VOL-001, VOL-011, VOL-350 | Dimensionality reduction anticipated dense semantic search while exposing interpretability and drift tradeoffs. |
| `HIST-AI-032` | PageRank | graph ranking | VOL-001, VOL-012, VOL-354 | Link structure can encode useful authority signals, but popularity is not truth. |
| `HIST-AI-033` | Blackboard architectures | multi-agent | VOL-001, VOL-017, VOL-201 | Independent specialists publishing partial solutions remain relevant to agent coordination and shared evidence stores. |
| `HIST-AI-034` | Pandemonium architecture | ensemble systems | VOL-001, VOL-008, VOL-206 | Competing recognizers are an early example of ensemble/specialist arbitration. |
| `HIST-AI-035` | Stigmergy | swarm | VOL-001, VOL-017, VOL-024 | Indirect coordination through environmental traces inspired swarm systems; stale traces and feedback loops must be controlled. |
| `HIST-AI-036` | Ant Colony Optimization | swarm/search | VOL-001, VOL-017, VOL-023 | Pheromone-style reinforcement can solve search problems but is sensitive to premature convergence. |
| `HIST-AI-037` | Monte Carlo Tree Search | search/planning | VOL-001, VOL-013, VOL-019, VOL-251 | Search with rollout/evaluation motivates bounded test-time search and simulation-backed planning. |
| `HIST-AI-038` | Alpha-beta search | search | VOL-001, VOL-013, VOL-152 | Strong pruning depends on evaluation quality and ordering; analogous verifier quality controls search efficiency. |
| `HIST-AI-039` | A* search | planning/search | VOL-001, VOL-014, VOL-370 | Heuristics must be evaluated for admissibility/consistency when correctness claims depend on optimality. |
| `HIST-AI-040` | Constraint satisfaction | constraints | VOL-001, VOL-303, VOL-315 | Explicit domains/constraints are often more reliable than free-form generation for configuration and scheduling. |
| `HIST-SYS-001` | Actor model | distributed systems | VOL-017, VOL-030, VOL-201 | Isolated state plus message passing informs agent/service ownership and supervision. |
| `HIST-SYS-002` | Communicating Sequential Processes | concurrency | VOL-030, VOL-131, VOL-306 | Explicit channels and process composition remain useful for reasoning about concurrent workflows. |
| `HIST-SYS-003` | Petri nets | formal workflow | VOL-081, VOL-127, VOL-371 | Tokens/places/transitions provide a rigorous way to analyze workflow reachability, deadlocks and boundedness. |
| `HIST-SYS-004` | Linda tuple spaces | coordination | VOL-017, VOL-030, VOL-331 | Generative communication via shared tuples is a historical cousin of blackboards, queues and shared workspaces. |
| `HIST-SYS-005` | Erlang supervision trees | resilience | VOL-029, VOL-030, VOL-282 | Let-it-crash works only with isolation, supervisors, restart strategy and durable external state. |
| `HIST-SYS-006` | Tandem NonStop | fault tolerance | VOL-029, VOL-065, VOL-189 | Fault containment and replicated process pairs demonstrate designing for component failure as normal operation. |
| `HIST-SYS-007` | Write-ahead logging | persistence | VOL-005, VOL-029, VOL-133 | Durability before acknowledgement is foundational for recoverable state transitions. |
| `HIST-SYS-008` | MVCC | databases | VOL-005, VOL-132, VOL-299 | Snapshot isolation enables concurrency but introduces stale-read and write-skew edge cases. |
| `HIST-SYS-009` | Two-phase commit | distributed transactions | VOL-030, VOL-133, VOL-380 | Atomic cross-system commits are costly and fragile under coordinator failure; prefer narrower transactions where possible. |
| `HIST-SYS-010` | Sagas | distributed transactions | VOL-015, VOL-133, VOL-379, VOL-380 | Compensating long transactions map naturally to tool workflows with external side effects. |
| `HIST-SYS-011` | Lamport clocks | distributed time | VOL-030, VOL-297, VOL-299 | Causal ordering can be represented without trusting wall clocks. |
| `HIST-SYS-012` | Vector clocks | distributed time | VOL-030, VOL-297, VOL-299 | Partial ordering helps distinguish concurrency from overwrite order, especially in distributed state. |
| `HIST-SYS-013` | Chandy-Lamport snapshots | distributed state | VOL-030, VOL-034, VOL-284 | Consistent distributed snapshots show that observing a system is itself a protocol problem. |
| `HIST-SYS-014` | Paxos | consensus | VOL-030, VOL-081 | Consensus safety depends on precise invariants; simplified retellings often omit failure subtleties. |
| `HIST-SYS-015` | Raft | consensus | VOL-030, VOL-081 | Understandable consensus still requires disciplined membership, log and snapshot handling. |
| `HIST-SYS-016` | FLP impossibility | distributed systems | VOL-030, VOL-081, VOL-188 | Asynchrony plus crash failures means guaranteed deterministic consensus termination is impossible without stronger assumptions. |
| `HIST-SYS-017` | CAP theorem | distributed systems | VOL-030, VOL-132 | Partition behavior must be explicit; CAP is not a generic excuse to ignore consistency design. |
| `HIST-SYS-018` | End-to-end principle | architecture | VOL-002, VOL-037, VOL-060 | Some correctness properties belong at the application boundary even when lower layers provide partial guarantees. |
| `HIST-SYS-019` | Capability security | security | VOL-026, VOL-028, VOL-165 | Unforgeable scoped capabilities map cleanly to tool/agent authority. |
| `HIST-SYS-020` | Saltzer–Schroeder principles | security | VOL-025, VOL-026, VOL-167 | Least privilege, fail-safe defaults, complete mediation and economy of mechanism remain central AI-tool security lessons. |
| `HIST-SYS-021` | Bell-LaPadula / Biba | information security | VOL-026, VOL-027, VOL-348 | Confidentiality and integrity models show why data policy has more than one axis. |
| `HIST-SYS-022` | Microkernels | architecture | VOL-002, VOL-004, VOL-053 | Keep the trusted core small; move optional capability outward behind explicit interfaces. |
| `HIST-SYS-023` | Unix pipes | composition | VOL-015, VOL-373 | Composable small tools are valuable, but untyped text boundaries become brittle at scale. |
| `HIST-SYS-024` | Plan 9 namespaces | namespaces | VOL-026, VOL-331, VOL-332 | Per-process namespaces foreshadow scoped resource views and capability-oriented workspace resolution. |
| `HIST-SYS-025` | Smalltalk image persistence | runtime state | VOL-005, VOL-063, VOL-272 | Persistent execution worlds are powerful but blur code/state boundaries; explicit migration and reproducibility remain essential. |
| `HIST-SYS-026` | MapReduce | distributed compute | VOL-030, VOL-400 | Separating map/shuffle/reduce clarifies data-parallel workflows and failure retry boundaries. |
| `HIST-SYS-027` | Google File System lineage | storage | VOL-005, VOL-029, VOL-395 | Designing around commodity failure emphasizes checksums, replication and recovery over assuming reliable disks. |
| `HIST-SYS-028` | Dynamo-style systems | distributed data | VOL-030, VOL-132, VOL-359 | Quorums and eventual consistency introduce sibling/conflict resolution that applications must understand. |
| `HIST-SYS-029` | Bigtable lineage | data systems | VOL-005, VOL-395, VOL-396 | Sorted keyspaces and locality-aware design show why access patterns should drive storage architecture. |
| `HIST-SYS-030` | Borg-style cluster scheduling | scheduling | VOL-030, VOL-286, VOL-287 | Resource reservations, priorities and preemption inform agent/build/research workload isolation. |

## Concrete edge and failure cases

| ID | Edge case | Domain | Mapped volumes | Required lesson |
| --- | --- | --- | --- | --- |
| `EDGE-CONTRACT-001` | Duplicate JSON object keys | serialization | VOL-003, VOL-129, VOL-198 | Different parsers may keep first or last value; reject duplicates for security-sensitive contracts. |
| `EDGE-CONTRACT-002` | Missing versus explicit null | schema semantics | VOL-003, VOL-129, VOL-130 | Treating absent and null as identical can erase defaults or permissions. |
| `EDGE-CONTRACT-003` | Unknown enum value after rolling upgrade | versioning | VOL-003, VOL-130 | Old consumers must fail safely or preserve unknown values rather than misclassify. |
| `EDGE-CONTRACT-004` | Unknown fields stripped then reserialized | versioning | VOL-003, VOL-130, VOL-131 | Intermediate services can destroy forward-compatible data. |
| `EDGE-CONTRACT-005` | NaN and Infinity in JSON-adjacent stacks | serialization | VOL-003, VOL-129, VOL-198 | Some serializers accept non-standard numeric values that others reject or compare oddly. |
| `EDGE-CONTRACT-006` | Negative zero | numeric edge | VOL-003, VOL-129 | -0.0 can produce surprising hashing, display and comparison behavior. |
| `EDGE-CONTRACT-007` | Integer precision above JavaScript safe range | numeric edge | VOL-003, VOL-041, VOL-298 | IDs/counters may silently round in browser clients. |
| `EDGE-CONTRACT-008` | Unicode normalization mismatch | text edge | VOL-003, VOL-086, VOL-298 | Visually identical strings may hash or compare differently. |
| `EDGE-CONTRACT-009` | Bidirectional control characters | text/security | VOL-026, VOL-079, VOL-198 | Bidi markers can make source, paths or identifiers visually misleading. |
| `EDGE-CONTRACT-010` | Zero-width and confusable characters | text/security | VOL-026, VOL-079, VOL-298 | Identifiers and policy strings can be spoofed through invisible or lookalike code points. |
| `EDGE-CONTRACT-011` | Case folding differences | portability | VOL-031, VOL-043, VOL-298 | Windows/macOS/Linux/path stores may disagree on identifier uniqueness. |
| `EDGE-CONTRACT-012` | Trailing whitespace/control characters | text edge | VOL-003, VOL-026 | Credentials, filenames or IDs may compare differently after normalization. |
| `EDGE-CONTRACT-013` | Locale-sensitive casing | internationalization | VOL-086, VOL-298 | Turkish-I-style transformations can corrupt normalized identifiers. |
| `EDGE-CONTRACT-014` | Timezone offset ambiguity | time | VOL-005, VOL-297 | Wall-clock timestamps without offsets break ordering and retention logic. |
| `EDGE-CONTRACT-015` | DST fold/gap | time | VOL-063, VOL-297 | Local times can occur twice or never occur; internal deadlines must not rely on local wall time. |
| `EDGE-CONTRACT-016` | Leap-second / clock-step assumptions | time | VOL-029, VOL-297 | Duration logic should use monotonic clocks rather than wall-clock subtraction. |
| `EDGE-CONTRACT-017` | Extremely long IDs/strings | resource abuse | VOL-025, VOL-041, VOL-129 | Valid-but-huge fields can become memory/DB/log amplification attacks. |
| `EDGE-CONTRACT-018` | Empty collection semantics | schema semantics | VOL-003, VOL-129 | Empty may mean clear-all, no-op, or none-selected; contracts must specify it. |
| `EDGE-CONTRACT-019` | Map ordering assumptions | determinism | VOL-003, VOL-296, VOL-299 | Hash-map iteration order must never become protocol semantics accidentally. |
| `EDGE-CONTRACT-020` | Canonicalization before signing | provenance/security | VOL-038, VOL-178, VOL-275 | Equivalent documents can hash differently unless signing format is canonical. |
| `EDGE-DIST-001` | Lost acknowledgement after successful commit | distributed failure | VOL-029, VOL-133, VOL-295 | Caller retries and duplicates the action unless idempotency is durable. |
| `EDGE-DIST-002` | Duplicate event delivery | messaging | VOL-029, VOL-134, VOL-294 | Consumers must be idempotent and maintain inbox/dedup state. |
| `EDGE-DIST-003` | Out-of-order events | messaging | VOL-039, VOL-040, VOL-299 | Sequence/version checks must reject stale transitions. |
| `EDGE-DIST-004` | Event gap during reconnect | streaming | VOL-040, VOL-045, VOL-295 | Clients need resumable cursors and gap recovery from durable state. |
| `EDGE-DIST-005` | Terminal event emitted before durable final result | finalization | VOL-039, VOL-040, VOL-097 | UI can show completion for an operation that cannot be reconstructed. |
| `EDGE-DIST-006` | Process crash after external side effect but before receipt | side effects | VOL-015, VOL-029, VOL-378 | Blind retry can duplicate irreversible action. |
| `EDGE-DIST-007` | Stale lease holder resumes | leases | VOL-017, VOL-030, VOL-398 | Fencing token must prevent zombie worker commits. |
| `EDGE-DIST-008` | Lease expires during long syscall | leases | VOL-017, VOL-029, VOL-398 | Renewal and commit fencing must be independent of worker optimism. |
| `EDGE-DIST-009` | ABA state change | concurrency | VOL-005, VOL-030, VOL-299 | A value changes A→B→A and naive equality misses that history changed. |
| `EDGE-DIST-010` | Split brain | distributed failure | VOL-030, VOL-081, VOL-188 | Two coordinators believe they own the same scope; quorum/fencing rules must choose authority. |
| `EDGE-DIST-011` | Network partition with healthy processes | distributed failure | VOL-029, VOL-030, VOL-180 | Health checks alone cannot distinguish isolation from service death. |
| `EDGE-DIST-012` | Retry storm | resilience | VOL-029, VOL-290, VOL-291 | Failures trigger retries that create enough load to prevent recovery. |
| `EDGE-DIST-013` | Reconnect storm | resilience | VOL-040, VOL-288, VOL-289 | Thousands of clients reconnect simultaneously after outage. |
| `EDGE-DIST-014` | Thundering herd on cache miss | cache | VOL-135, VOL-286, VOL-288 | Many workers regenerate the same expensive value. |
| `EDGE-DIST-015` | Cache stampede after TTL boundary | cache | VOL-135, VOL-288 | Synchronized expiry creates burst load; jitter/single-flight may be required. |
| `EDGE-DIST-016` | Poison message | queue | VOL-029, VOL-291, VOL-294 | One permanently invalid task is retried forever without dead-lettering. |
| `EDGE-DIST-017` | Head-of-line blocking | queue | VOL-030, VOL-286, VOL-288 | One slow item prevents independent work behind it. |
| `EDGE-DIST-018` | Priority inversion | scheduler | VOL-030, VOL-287 | Low-priority holder blocks high-priority work through shared lock/resource. |
| `EDGE-DIST-019` | Starvation | scheduler | VOL-030, VOL-287 | Fairness policy may indefinitely delay low-priority work. |
| `EDGE-DIST-020` | Livelock | autonomy/reliability | VOL-018, VOL-029, VOL-317 | Workers remain active and retry/replan without making progress. |
| `EDGE-DIST-021` | Deadlock | concurrency | VOL-030, VOL-081, VOL-371 | Cyclic waits across leases/resources can stop progress while all processes look healthy. |
| `EDGE-DIST-022` | Clock skew invalidates lease math | time/distributed | VOL-030, VOL-297, VOL-299 | Lease safety cannot depend solely on synchronized wall clocks. |
| `EDGE-DIST-023` | Read-after-write not guaranteed | consistency | VOL-005, VOL-132 | Eventual stores may not immediately reflect accepted writes. |
| `EDGE-DIST-024` | Write skew under snapshot isolation | database | VOL-005, VOL-132, VOL-199 | Concurrent transactions each satisfy local checks yet violate global invariant. |
| `EDGE-DIST-025` | Partial multi-store update | state convergence | VOL-005, VOL-133, VOL-352 | Canonical DB succeeds but derived index fails; reconciliation must know which is authoritative. |
| `EDGE-DIST-026` | Outbox row committed but publisher dies | eventing | VOL-133, VOL-134, VOL-295 | Dispatcher must resume safely and publish once-or-duplicate-tolerantly. |
| `EDGE-DIST-027` | Consumer commits side effect before inbox marker | eventing | VOL-134, VOL-295 | Crash permits duplicate effect on replay. |
| `EDGE-DIST-028` | Queue invisibility timeout too short | queue | VOL-030, VOL-294 | Slow valid worker causes duplicate concurrent execution. |
| `EDGE-DIST-029` | Backpressure ignored by producer | capacity | VOL-288, VOL-289 | Memory and queue growth becomes outage amplification. |
| `EDGE-DIST-030` | Cancellation races with completion | operation state | VOL-004, VOL-029, VOL-127 | Terminal state must deterministically resolve concurrent cancel/success commits. |
| `EDGE-AI-001` | Indirect prompt injection in retrieved document | AI security | VOL-009, VOL-025, VOL-168 | External evidence must remain data, never inherit instruction authority. |
| `EDGE-AI-002` | Instruction laundering through tool output | AI security | VOL-015, VOL-025, VOL-377 | A tool result containing commands cannot self-authorize subsequent tools. |
| `EDGE-AI-003` | Memory poisoning | memory security | VOL-010, VOL-168, VOL-362 | Incorrect or malicious content persisted as durable memory can corrupt future sessions. |
| `EDGE-AI-004` | Stale memory overrides current user intent | memory | VOL-010, VOL-329, VOL-365 | Recency/scope and explicit user instruction must outrank old inferred memory. |
| `EDGE-AI-005` | Retrieval citation laundering | evidence | VOL-011, VOL-012, VOL-355 | Ten pages quoting one false origin are not ten independent sources. |
| `EDGE-AI-006` | Semantic duplicate evidence | evidence | VOL-012, VOL-355, VOL-356 | Near-duplicate claims can inflate apparent corroboration. |
| `EDGE-AI-007` | Chunk boundary severs qualifier | retrieval | VOL-011, VOL-138, VOL-357 | A retrieved sentence may lose the negation/limitation in adjacent text. |
| `EDGE-AI-008` | Wrong temporal scope | knowledge | VOL-012, VOL-246, VOL-247 | Historically true evidence is applied as current fact. |
| `EDGE-AI-009` | Wrong population/domain scope | knowledge | VOL-012, VOL-357 | Evidence from one environment is generalized to another without support. |
| `EDGE-AI-010` | Embedding-model mismatch | retrieval | VOL-011, VOL-350, VOL-351 | Query/index embeddings from different spaces can silently destroy retrieval quality. |
| `EDGE-AI-011` | Stale vector index after source deletion | governance | VOL-011, VOL-177, VOL-352 | Deleted content remains retrievable from a derived index. |
| `EDGE-AI-012` | Context compression drops exception | context | VOL-009, VOL-117, VOL-254 | Summarization preserves the rule but loses its critical caveat. |
| `EDGE-AI-013` | Policy trimmed from long context | context/security | VOL-009, VOL-118 | Mandatory policy must live outside optional truncation budget. |
| `EDGE-AI-014` | Tool schema version race | tools/contracts | VOL-015, VOL-129, VOL-376 | Model sees v1 schema while executor validates v2. |
| `EDGE-AI-015` | Duplicate model tool-call IDs | provider/tool | VOL-007, VOL-015, VOL-083 | Provider output normalization must reject ambiguous call identity. |
| `EDGE-AI-016` | Malformed partial structured output | model output | VOL-007, VOL-040, VOL-129 | Streaming JSON may be valid only at terminal completion; parser must not commit partial objects. |
| `EDGE-AI-017` | Provider finishes stream without terminal usage | provider accounting | VOL-007, VOL-034, VOL-186 | Usage must be explicit unknown, not zero. |
| `EDGE-AI-018` | Provider alias silently changes model revision | model governance | VOL-006, VOL-179, VOL-411 | Registry must resolve immutable deployment identity for reproducible evals. |
| `EDGE-AI-019` | Tokenizer changes under same model family | model lifecycle | VOL-006, VOL-179, VOL-240 | Context-length and cost assumptions can drift after tokenizer updates. |
| `EDGE-AI-020` | Fallback model lacks required modality/tool support | routing | VOL-008, VOL-228 | Fallback must re-check hard constraints, not just provider availability. |
| `EDGE-AI-021` | Fallback changes privacy boundary | routing/privacy | VOL-008, VOL-027, VOL-228 | A request allowed locally may be forbidden from remote failover. |
| `EDGE-AI-022` | Model repeats same failing tool forever | autonomy | VOL-018, VOL-113, VOL-253 | Stagnation detector must stop identical proposal/error cycles. |
| `EDGE-AI-023` | Verifier shares same correlated error | verification | VOL-037, VOL-152, VOL-208 | Independent verification needs diversity of evidence/process, not merely another sample. |
| `EDGE-AI-024` | False consensus among agents | multi-agent | VOL-017, VOL-206, VOL-208 | Many agents using same model/context are not independent votes. |
| `EDGE-AI-025` | Judge position/order bias | evaluation | VOL-035, VOL-206, VOL-220 | Candidate ordering can alter evaluator preference; randomize/blind where appropriate. |
| `EDGE-AI-026` | Benchmark contamination | evaluation | VOL-035, VOL-219 | Training/retrieval exposure invalidates naive performance interpretation. |
| `EDGE-AI-027` | Hidden test leakage through tool/search access | evaluation | VOL-217, VOL-219 | Agent eval environments must isolate held-out ground truth. |
| `EDGE-AI-028` | Reward hacking / specification gaming | alignment | VOL-024, VOL-324 | Agent optimizes metric while violating intended objective. |
| `EDGE-AI-029` | Sycophancy overrides evidence | answer quality | VOL-013, VOL-254, VOL-328 | User preference should not silently outrank verified factual evidence. |
| `EDGE-AI-030` | Hallucinated authorization | authority | VOL-028, VOL-256 | Generated text claiming approval has no authority unless bound to durable approval state. |
| `EDGE-AI-031` | Approval becomes stale after argument edit | approval | VOL-015, VOL-256, VOL-378 | Changing exact tool arguments invalidates prior approval digest. |
| `EDGE-AI-032` | Approval expires while queued | approval | VOL-015, VOL-028, VOL-256 | Execution must revalidate expiry and policy at point of use. |
| `EDGE-AI-033` | Memory feedback loop | memory/evidence | VOL-010, VOL-012, VOL-362 | Model output becomes memory, memory becomes evidence, then self-reinforces without external support. |
| `EDGE-AI-034` | Retrieval feedback loop | retrieval/evidence | VOL-011, VOL-012, VOL-139 | Generated summary gets indexed and later cited as if independent source. |
| `EDGE-AI-035` | Self-improvement evaluator overfits candidate | evolution | VOL-024, VOL-035, VOL-415 | Promotion requires held-out/adversarial comparisons against champion. |
| `EDGE-AI-036` | Long-horizon goal drift | autonomy | VOL-018, VOL-323, VOL-325 | Agent remains busy but drifts from original objective through local optimizations. |
| `EDGE-AI-037` | Tool result too large for context | context/tools | VOL-009, VOL-015, VOL-255 | Result must be bounded/stored/referenced instead of blindly injected. |
| `EDGE-AI-038` | Model refusal semantics differ by provider | providers | VOL-007, VOL-090, VOL-100 | Normalized result must distinguish refusal, policy block, provider error and empty answer. |
| `EDGE-AI-039` | Partial tool success | tools | VOL-015, VOL-378, VOL-379 | A tool may perform some side effects before reporting failure; receipts need postcondition/reconciliation. |
| `EDGE-AI-040` | Unknown external effect after timeout | tools | VOL-015, VOL-029, VOL-378 | Timeout does not prove non-execution; reconciliation is required before retry. |
| `EDGE-SEC-001` | TOCTOU authorization race | security | VOL-026, VOL-028, VOL-337 | Resource can change between authorization and use; bind checks to version/snapshot where needed. |
| `EDGE-SEC-002` | Symlink escape | filesystem security | VOL-026, VOL-164 | Path allowed at validation can resolve outside sandbox at execution. |
| `EDGE-SEC-003` | Hardlink aliasing | filesystem security | VOL-026, VOL-164 | Different paths can refer to same inode and bypass naive path-only policies. |
| `EDGE-SEC-004` | Path traversal after decoding | filesystem/web security | VOL-026, VOL-164 | Percent/Unicode/double decoding can reintroduce ../ semantics. |
| `EDGE-SEC-005` | Zip Slip | artifact security | VOL-025, VOL-075, VOL-164 | Archive entries can escape destination if paths are not normalized and rooted. |
| `EDGE-SEC-006` | Tarbomb / decompression bomb | artifact security | VOL-025, VOL-075, VOL-164 | Small compressed input can expand beyond disk/memory budgets. |
| `EDGE-SEC-007` | Archive symlink chain | artifact security | VOL-025, VOL-075, VOL-164 | Safe-looking archive path can become unsafe after extracting symlink entries. |
| `EDGE-SEC-008` | Windows reserved device names | portability/security | VOL-031, VOL-043, VOL-164 | CON/NUL/AUX and similar names can behave unlike normal files. |
| `EDGE-SEC-009` | Alternate data streams | filesystem security | VOL-026, VOL-075 | Windows ADS can hide content from naive file scanners. |
| `EDGE-SEC-010` | Case-insensitive path collision | supply chain | VOL-026, VOL-051, VOL-273 | Two logical files collapse to one on another platform. |
| `EDGE-SEC-011` | DNS rebinding | network security | VOL-026, VOL-171, VOL-172 | Hostname passes policy then resolves to blocked/private destination later. |
| `EDGE-SEC-012` | Redirect crosses egress boundary | network security | VOL-026, VOL-171, VOL-172 | Allowed public URL redirects into forbidden network/address. |
| `EDGE-SEC-013` | Metadata-service SSRF | network security | VOL-026, VOL-171, VOL-172 | Cloud metadata endpoints require explicit blocking independent of hostname text. |
| `EDGE-SEC-014` | IPv4-mapped IPv6 bypass | network security | VOL-026, VOL-171, VOL-172 | Address checks must normalize equivalent representations. |
| `EDGE-SEC-015` | Secret in exception/log payload | secrets/observability | VOL-026, VOL-034, VOL-173 | Redaction must apply across nested errors, traces and retries. |
| `EDGE-SEC-016` | Environment-variable inheritance | process security | VOL-026, VOL-164, VOL-173 | Child process receives secrets it did not need. |
| `EDGE-SEC-017` | Temporary-file race | filesystem security | VOL-026, VOL-164 | Predictable paths/symlinks can redirect privileged writes. |
| `EDGE-SEC-018` | Shell quoting divergence | process security | VOL-026, VOL-043, VOL-164 | Arguments safe in POSIX shell may be unsafe in Windows cmd/PowerShell and vice versa. |
| `EDGE-SEC-019` | Executable shadowing via PATH | process security | VOL-026, VOL-164 | Spawned command may resolve attacker-controlled binary. |
| `EDGE-SEC-020` | Stale credential after revocation | identity | VOL-026, VOL-028, VOL-173 | Long-lived worker cache must not continue using revoked authority indefinitely. |
| `EDGE-DATA-001` | Tombstone resurrection | data lifecycle | VOL-005, VOL-177, VOL-352 | Old replica/index rebuild can reintroduce deleted data. |
| `EDGE-DATA-002` | Orphaned blob after metadata rollback | artifact lifecycle | VOL-005, VOL-075, VOL-177 | Object exists without reachable metadata and escapes normal retention. |
| `EDGE-DATA-003` | Metadata points to missing blob | artifact integrity | VOL-005, VOL-075, VOL-189 | Canonical reference exists but object store lost content. |
| `EDGE-DATA-004` | Hash collision assumption | integrity | VOL-075, VOL-136, VOL-275 | Content hashes need algorithm/version metadata and collision-response strategy. |
| `EDGE-DATA-005` | Corrupt backup discovered only during restore | recovery | VOL-064, VOL-065, VOL-189 | Backup success is not recovery evidence; restore drills are mandatory. |
| `EDGE-DATA-006` | Migration partially applied | migration | VOL-005, VOL-063, VOL-260 | Schema/data version markers must not declare success before post-validation. |
| `EDGE-DATA-007` | Rollback code cannot read new data shape | migration/release | VOL-060, VOL-193, VOL-260 | Backward compatibility must be validated before release. |
| `EDGE-DATA-008` | Index built from inconsistent source snapshot | indexing | VOL-011, VOL-352, VOL-360 | Derived search can represent impossible mixed-time state. |
| `EDGE-DATA-009` | Data retention applies to source but not derived embedding | privacy | VOL-027, VOL-177, VOL-350 | Derived representations need deletion propagation. |
| `EDGE-DATA-010` | Backup retains deleted sensitive data | privacy/recovery | VOL-027, VOL-064, VOL-177 | Policy must document delayed erasure in immutable backups. |
| `EDGE-HW-001` | Disk full during atomic write | hardware/recovery | VOL-029, VOL-031, VOL-064 | Temporary/write-ahead files can consume final free space; failure must preserve prior good state. |
| `EDGE-HW-002` | Inode exhaustion with free bytes | hardware | VOL-031, VOL-067 | Filesystem may fail creation despite apparent capacity. |
| `EDGE-HW-003` | GPU reset mid-inference | inference reliability | VOL-007, VOL-029, VOL-381 | Worker/model state must be discarded or reinitialized safely. |
| `EDGE-HW-004` | VRAM fragmentation | GPU scheduling | VOL-031, VOL-383 | Enough total free VRAM may exist without a large contiguous allocation. |
| `EDGE-HW-005` | Mixed-precision overflow/underflow | training | VOL-006, VOL-147 | Numerical health checks must detect NaN/Inf and unstable training. |
| `EDGE-HW-006` | Nondeterministic GPU kernels | evaluation | VOL-078, VOL-184, VOL-296 | Reproducibility claims must record nondeterministic execution paths. |
| `EDGE-HW-007` | Thermal throttling | performance | VOL-031, VOL-067, VOL-184 | Latency/throughput baselines can drift under sustained load. |
| `EDGE-HW-008` | NUMA remote-memory penalty | performance | VOL-031, VOL-393 | CPU-heavy/vector workloads may degrade unexpectedly on multi-socket hosts. |
| `EDGE-HW-009` | Suspend/resume invalidates timers/connections | desktop | VOL-043, VOL-049, VOL-297 | Desktop runtime must recover from laptop sleep and network change. |
| `EDGE-HW-010` | Driver/runtime version mismatch | installer/hardware | VOL-031, VOL-047 | Hardware exists but required accelerator stack is incompatible. |
| `EDGE-UX-001` | Double-submit across tabs | product | VOL-042, VOL-045, VOL-097 | Idempotency must be server-side, not a disabled button. |
| `EDGE-UX-002` | Browser refresh during running operation | product continuity | VOL-040, VOL-042, VOL-097 | Client rebuilds from durable operation/event state. |
| `EDGE-UX-003` | Offline draft later submitted twice | offline/product | VOL-044, VOL-229 | Queued local intents need stable client-generated idempotency identity. |
| `EDGE-UX-004` | Cancel clicked after server completed | product state | VOL-042, VOL-045, VOL-127 | UI must reconcile canonical terminal state rather than fabricate cancellation. |
| `EDGE-UX-005` | Stale optimistic update | product state | VOL-042, VOL-045, VOL-132 | Server version conflict should visibly reconcile rather than silently overwrite. |
| `EDGE-UX-006` | Huge streaming output freezes UI | performance/UX | VOL-040, VOL-042, VOL-045 | Rendering needs chunking/virtualization and bounded retained transcript DOM. |
| `EDGE-UX-007` | Screen reader misses streaming status | accessibility | VOL-045, VOL-086 | Progress and terminal states require accessible announcements. |
| `EDGE-UX-008` | Locale changes numeric meaning | internationalization | VOL-086, VOL-129 | Never parse invariant machine values using presentation locale. |
| `EDGE-UX-009` | User clock wildly wrong | time/UX | VOL-042, VOL-297 | Deadlines/status use server authority; client clock is presentation-only. |
| `EDGE-UX-010` | Multi-device concurrent conversation append | conversation | VOL-023, VOL-097, VOL-132 | Thread sequencing/versioning must resolve concurrent valid writers. |

## Obscure but high-value architecture lessons

| ID | Pattern | Domain | Mapped volumes | Skeleton lesson |
| --- | --- | --- | --- | --- |
| `OBSCURE-001` | Failure detectors are suspicion, not truth | distributed theory | VOL-030, VOL-180, VOL-188 | Distributed systems commonly use imperfect failure detectors; architecture should distinguish 'unreachable' from 'dead'. |
| `OBSCURE-002` | Exactly-once is usually an end-to-end property | messaging | VOL-133, VOL-134, VOL-295 | Transport can provide at-least-once while application idempotency produces one canonical effect. |
| `OBSCURE-003` | Fencing is stronger than locks alone | concurrency | VOL-017, VOL-030, VOL-398 | A stale lock holder can still commit unless the guarded resource verifies a monotonically newer token. |
| `OBSCURE-004` | Cancellation is a protocol | operations | VOL-004, VOL-015, VOL-029 | Stopping local work does not undo remote side effects or messages already committed. |
| `OBSCURE-005` | Timeout means unknown, not failed | distributed operations | VOL-015, VOL-029, VOL-378 | After an external timeout the action may have succeeded; query/reconcile before retry. |
| `OBSCURE-006` | Derived indexes are disposable only if source truth is complete | data architecture | VOL-005, VOL-011, VOL-189 | Calling a store 'cache' is unsafe unless rebuild is proven from canonical state. |
| `OBSCURE-007` | Garbage collection is part of data architecture | data lifecycle | VOL-010, VOL-075, VOL-361 | Memory/artifact/index systems need reachability, retention and tombstone semantics. |
| `OBSCURE-008` | Negative caching can preserve outages | cache | VOL-135, VOL-228 | Caching 'not found' or provider failure can extend a transient incident. |
| `OBSCURE-009` | Jitter is a correctness aid under correlated retry | resilience | VOL-029, VOL-291 | Randomized retry timing prevents synchronized clients from becoming a denial-of-service amplifier. |
| `OBSCURE-010` | Read repair can resurrect stale data | distributed data | VOL-132, VOL-177, VOL-359 | Anti-entropy mechanisms require tombstone/version discipline. |
| `OBSCURE-011` | Checksums verify bytes, not meaning | integrity | VOL-038, VOL-075, VOL-139 | Semantically wrong data can have a perfect hash. |
| `OBSCURE-012` | Schema validation is not semantic validation | tools | VOL-015, VOL-037, VOL-165 | Well-formed tool arguments can still be unauthorized, nonsensical or dangerous. |
| `OBSCURE-013` | A successful process exit is not proof of intended effect | verification | VOL-015, VOL-037, VOL-378 | Postconditions matter for compilers, deploys, DB tools and external APIs. |
| `OBSCURE-014` | Backups are write-only until restoration is proven | operations | VOL-064, VOL-065, VOL-189 | Recovery drills are the evidence, not backup job success. |
| `OBSCURE-015` | Metrics can lie by omission | observability | VOL-034, VOL-180, VOL-182 | Sampling, cardinality limits and aggregation can hide tail failures. |
| `OBSCURE-016` | Average latency hides queue collapse | performance | VOL-067, VOL-180, VOL-290 | Tail latency and oldest-item age are critical under congestion. |
| `OBSCURE-017` | Fair scheduling can reduce throughput | scheduler economics | VOL-286, VOL-287, VOL-404 | Fairness and utilization are competing objectives that should be explicit. |
| `OBSCURE-018` | Compression changes trust geometry | context security | VOL-009, VOL-118, VOL-139 | A summary may merge trusted policy with untrusted evidence unless provenance survives compaction. |
| `OBSCURE-019` | Consensus among correlated models is not independent evidence | AI evaluation | VOL-206, VOL-208, VOL-220 | Diversity of mechanism/source matters more than vote count. |
| `OBSCURE-020` | Abstention is a valid successful outcome | verification | VOL-037, VOL-248, VOL-253 | Some high-uncertainty tasks should terminate qualified/unknown instead of fabricate completion. |
| `OBSCURE-021` | Unknown usage must stay unknown | economics | VOL-034, VOL-069, VOL-186 | Treating missing token/cost data as zero corrupts budgets and optimization. |
| `OBSCURE-022` | Policy version belongs in receipts | governance | VOL-028, VOL-038, VOL-165 | A later audit must know which exact rules admitted an action. |
| `OBSCURE-023` | Model version belongs in evidence lineage | model governance | VOL-179, VOL-216, VOL-411 | Provider aliases and silent model refreshes otherwise destroy reproducibility. |
| `OBSCURE-024` | Tool description is attacker-controlled context unless curated | tool security | VOL-015, VOL-025, VOL-160 | Descriptions can contain instructions; authority logic must remain out-of-band. |
| `OBSCURE-025` | Capability discovery can become privilege discovery | tool security | VOL-015, VOL-026, VOL-376 | Do not expose sensitive tool existence/details to principals lacking access. |
| `OBSCURE-026` | Silence is not agreement in multi-agent systems | multi-agent | VOL-017, VOL-206 | Missing reviewer response must not be counted as consensus. |
| `OBSCURE-027` | A lease is not ownership history | leases | VOL-017, VOL-038, VOL-398 | Audit needs acquisition/renewal/expiry/fencing events, not just current holder. |
| `OBSCURE-028` | Wall-clock timestamps cannot prove causality | time | VOL-297, VOL-299 | Use logical sequencing/versioning for causally ordered operations. |
| `OBSCURE-029` | Hash-based CAS still needs metadata migrations | artifacts | VOL-075, VOL-136, VOL-260 | Immutable bytes can remain interpretable only with schema/codec/version lineage. |
| `OBSCURE-030` | Reproducibility and repeatability differ | research | VOL-078, VOL-213, VOL-272 | Same setup repeating versus independent recreation are distinct evidence strengths. |

## Edge-case promotion rule

When an implementation touches a mapped volume, relevant catalogue entries should be promoted into one or more executable forms:

```text
catalog entry
  -> requirement / invariant
  -> targeted regression test
  -> property/fuzz test
  -> chaos/failure injection
  -> observability signal
  -> runbook/recovery step
  -> acceptance evidence
```

Not every edge case requires all forms. Security-sensitive parsing may deserve fuzz/property tests; distributed failures may deserve chaos/recovery tests; historical lessons may influence an ADR or interface invariant.

## Historical architecture review checklist

When adopting an old or rediscovered pattern, explicitly ask:

1. What original problem did it solve?
2. Which assumptions made it work?
3. Which failure modes were discovered historically?
4. Which modern component is analogous?
5. Are we preserving the useful invariant or merely copying terminology?
6. Does the new system have stronger evidence than the historical baseline?
7. What would cause us to retire the technique?

## Mandatory obscure-case families for VS-001

The Functional AI vertical slice should deliberately test at least:

- duplicate submit/idempotency;
- process crash around provider/tool boundaries;
- approval stale after argument change;
- timeout with unknown external side effect;
- context truncation that attempts to drop mandatory policy;
- indirect prompt injection from retrieval/tool output;
- stale/deleted retrieval index entry;
- model fallback violating modality/privacy constraints;
- duplicate/out-of-order stream events and reconnect gaps;
- cancellation-versus-completion race;
- unknown usage accounting;
- browser refresh/reconstruction;
- multi-device concurrent message append;
- provider alias/model-version provenance;
- tool schema version mismatch.

## Mandatory obscure-case families for repository engineering

VS-002 should deliberately test:

- symlink/hardlink/path-normalization escapes;
- case-collision portability;
- stale lease/zombie writer;
- partial build/test success;
- process environment secret inheritance;
- archive traversal/decompression bombs;
- concurrent branch/file ownership conflicts;
- CI retry storms and stale-run cancellation;
- rollback after migration/config change;
- imported-code provenance and licensing.

## Mandatory historical principles to preserve

The project should retain these mechanisms even when implementations change:

- explicit preconditions/effects from classical planning;
- truth/assumption maintenance rather than silent overwrite;
- specialist coordination without assuming majority truth;
- content-addressed/associative memory concepts;
- strong sparse-retrieval baselines beside dense retrieval;
- deterministic control around probabilistic inference;
- capability security / least privilege;
- WAL/outbox/idempotency for durable side effects;
- logical ordering rather than wall-clock causality;
- supervision/failure containment;
- compensating transactions for long multi-system work;
- formal/state-machine thinking for leases, authority and promotion.

## Scope-freeze relationship

This catalogue expands depth beneath existing volumes. Adding another historical family or edge case does **not** justify a new top-level volume unless it introduces a genuinely new architecture domain that cannot be represented by Volumes 000–420.
