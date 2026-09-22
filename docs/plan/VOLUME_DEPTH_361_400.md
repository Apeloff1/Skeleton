# Volume Depth Pass 361–400

Architecture lane: `plan/volume-depth-041-080-20260922`

Machine authority: [`machine/ai_master_plan.json`](../../machine/ai_master_plan.json)

Depth pass: **DP-361-400 — Memory-strategy-to-build-farm depth**

This pass deepens memory quality/lifecycle, cognitive strategy and plan
verification, tool composition/trust/side effects/sagas, distributed inference,
hardware/topology/locality, remote execution/attestation, and build-farm
execution.

| Volume | Domain | Primary build intent |
| --- | --- | --- |
| VOL-361 | Memory Garbage Collection | Reclaim obsolete memory safely without deleting authoritative or still-referenced knowledge. |
| VOL-362 | Memory Quality Evaluation | Measure memory precision, relevance, freshness, provenance and utility by memory class. |
| VOL-363 | Memory Interference Testing | Detect harmful interaction among memories, instructions, tasks and users/projects. |
| VOL-364 | Memory Versioning | Version durable memory records and policies with supersession, compatibility and rollback semantics. |
| VOL-365 | Memory Reconciliation | Resolve duplicate/conflicting/superseded memories using provenance, scope, time and trust. |
| VOL-366 | Cognitive Strategy Registry | Register reasoning/planning/search strategies with applicability, cost, risks and evaluation evidence. |
| VOL-367 | Strategy Selection | Choose reasoning/search/planning strategy by task type, uncertainty, constraints, budget and measured performance. |
| VOL-368 | Reasoning Cost Accounting | Attribute tokens, time, tool calls, retries and model costs to reasoning stages/strategies. |
| VOL-369 | Reasoning Regression Tests | Detect degradation in task outcomes, factuality, robustness and resource use after reasoning changes. |
| VOL-370 | Plan Verifier | Verify generated plans against objective, constraints, authority, dependencies, resources and rollback requirements. |
| VOL-371 | Plan Static Analyzer | Analyze plans/workflows before execution for cycles, unreachable steps, missing inputs, deadlocks and unhandled failures. |
| VOL-372 | Plan Simulation | Simulate plan execution against models/twin/stubs to expose failure, cost, timing and dependency issues before real execution. |
| VOL-373 | Tool Composition Engine | Compose multiple tools into bounded workflows based on typed schemas, side effects and dependencies. |
| VOL-374 | Tool Dependency Graph | Track tool runtime/service/data dependencies for planning, health and impact analysis. |
| VOL-375 | Tool Health | Measure tool success, latency, errors, policy denials, dependency health and output quality. |
| VOL-376 | Tool Capability Discovery | Discover available tools/capabilities dynamically while enforcing registry/policy authority. |
| VOL-377 | Tool Result Trust | Classify/validate tool outputs by provenance, integrity, freshness and semantic trust before reuse. |
| VOL-378 | Side-Effect Ledger | Record intended, attempted, confirmed, unknown and compensated external effects with idempotency identity. |
| VOL-379 | Compensation Engine | Execute tested compensating actions for reversible distributed side effects under explicit authority. |
| VOL-380 | Saga Workflows | Coordinate long-running multi-step side effects with persisted state, compensation and recovery. |
| VOL-381 | Distributed Inference Control Plane | Coordinate model replicas, routing, capacity, versions and admission across inference workers. |
| VOL-382 | Model Placement | Place models on workers based on memory, accelerator, topology, affinity, demand and policy. |
| VOL-383 | GPU Memory Manager | Track GPU memory allocations/reservations for models, KV/cache and execution with safety margins. |
| VOL-384 | Model Eviction | Evict idle/lower-priority models safely under memory/capacity pressure while preserving loadable provenance. |
| VOL-385 | Model Warming | Preload models/caches based on demand forecasts with bounded resource/cost budgets. |
| VOL-386 | Continuous Batching Scheduler | Batch compatible inference requests dynamically while respecting latency, tenant, model and cancellation constraints. |
| VOL-387 | KV Cache Service | Manage attention KV cache with version/session/tenant isolation, capacity and invalidation. |
| VOL-388 | Prefix Cache | Reuse validated common prompt prefixes across compatible inference requests under strict scope/version rules. |
| VOL-389 | Speculative Inference | Use draft/verification models or techniques to reduce latency while preserving target-model semantics. |
| VOL-390 | Inference Autoscaling | Scale replicas/capacity from demand, latency, queue, memory and warmup signals with stability controls. |
| VOL-391 | Inference Load Testing | Benchmark inference throughput/latency/memory/error under representative concurrency, models and contexts. |
| VOL-392 | Hardware Topology Model | Represent hosts, CPUs, NUMA, accelerators, memory, interconnect, storage and network capabilities. |
| VOL-393 | NUMA Awareness | Place CPU/memory workloads with NUMA locality considerations where performance materially benefits. |
| VOL-394 | GPU Interconnect Awareness | Use NVLink/PCIe/fabric topology for multi-GPU model/tensor/pipeline placement and transfer planning. |
| VOL-395 | Storage Tiering | Place artifacts/datasets/checkpoints/caches across memory/local SSD/network/object/archive tiers by access, cost and durability. |
| VOL-396 | Data Locality | Schedule compute near required data/models while respecting privacy, residency and consistency constraints. |
| VOL-397 | Network Topology Awareness | Use bandwidth/latency/failure-domain topology for distributed scheduling and data/model transfer. |
| VOL-398 | Remote Execution Protocol | Execute bounded tasks on remote workers with authenticated identity, leases, artifact/input digests and result receipts. |
| VOL-399 | Worker Attestation | Establish worker software/config/environment identity before trust-sensitive execution/results are accepted. |
| VOL-400 | Build Farm | Distribute hermetic builds/tests across attested workers with cache/provenance/resource scheduling. |

## Remaining work after DP-361-400

- finish sequentially with **DP-401-420**;
- materialize memory/strategy/plan regression harnesses;
- bind tool effects/sagas to durable reconciliation;
- qualify inference topology/cache/autoscaling against representative load;
- require attestation and provenance in remote/build-farm execution.
