# GameForge / PROOD — Tech Stack & Advanced Architecture Blueprint
_Refactor blueprint v1 — "start with the tech stack". This is the PLAN; it documents the
current advanced stack and the staged path to make every layer more elaborate WITHOUT
destroying the running 99.6%-complete system._

> Guiding principle: **advanced ≠ deliberately convoluted.** We increase capability,
> observability, and rigor while keeping the system operable. "Byzantine" is embraced
> where it means *Byzantine-fault-tolerant* (consensus, quorums), not unmaintainable.

---

## 1. Current Tech Stack (source of truth)

### Frontend
- **Expo SDK 54 / React Native 0.81.5** (TypeScript), file-based routing via **expo-router**.
- State: React hooks + module singletons; `src/utils/apiClient` for all HTTP.
- Native: expo-file-system/legacy, expo-sharing, expo-clipboard, expo-secure-store.
- Charts/graphics: react-native-svg; StyleSheet only (no CSS/Tailwind on native).
- **Palette constraint: cyan is banned** (`#00FFFF`, `#0EA5E9`, sky/teal) — green/blue/purple/amber.

### Backend
- **FastAPI** (async), self-prefixed `APIRouter`s registered in `core/routes_registry.py`.
- **MongoDB** via `core/databases.get_sync_db()` (+ motor async where needed).
- Probability/ML: **numpy 2.4.4, scipy 1.17.1** (LAFS deep Bayes).
- LLM: **emergentintegrations** (Emergent Universal Key) — Claude/OpenAI/Gemini.
- HTTP egress: **httpx** (compliant UA required for Wikipedia REST).
- Native toolchains: **ARM64 Godot** headless, PyInstaller Linux builds.

### Platform
- Kubernetes pod; ingress routes `/api/*` → :8001, `/` → :3000 (Metro).
- Ephemeral `/tmp` (wiped on fork) → **all durable state must be in Mongo**.

---

## 2. Advanced Subsystems Already Live (16 PROOD capabilities @ 99.6%)

| # | Capability | Module | Notes |
|---|-----------|--------|-------|
| 1 | Churn Pipeline | `gameforge/workflow/autonomous_workflow.py` | exploit/explore, memory, directives |
| 2 | Resilience / 165+ gates | `resilience_forge`, `sentinel_array` | circuit breakers, self-heal |
| 3 | Quality Control | `quality_control` | standards/gates |
| 4 | Observability | `observability_v2` (`/health/runtime`, `/telemetry/trail`) | metrics/alerting |
| 5 | Saga & Workflow Orch. | `gameforge/prood/saga_orchestrator.py` | **real compensation/rollback** |
| 6 | Autonomous Workflow→Deploy | `workflow/*` + `routes/gameforge_workflow.py` | InternalBuild → JeevesVault |
| 7 | Multi-Agent Orchestration | `gameforge_runtime` | groupchat, heartbeats |
| 8 | Billing & Usage | `monetization_pipeline`, Stripe | quotas, plans |
| 9 | Governance & Audit | `governance` | reports/audit |
| 10 | CQRS · Event Sourcing · Bus | `gameforge/prood/event_bus.py` | error-isolated pub/sub |
| 11 | Real-time Collaboration | `collaboration` | sessions |
| 12 | Marketplace & Community | `marketplace`, `creator_economy` | listings/creators |
| 13 | Testing & QA | `testing_qa_pipeline` | overview |
| 14 | **Ω-Ultra Conductor** | `gameforge/omega/*` | never-repeat, causal DAG, Byzantine quorum, Kalman, Merkle |
| 15 | SOTA Engine Coverage | `gameforge/coverage` | 94% engines live |
| 16 | **LAFS Knowledge Ledger** | `gameforge/lafs/*` | hierarchical Bayes, EFE, MCMC/VI, **online learning** |

**Fabric topology:** `JEEVES (mastermap) → AGENT-MAP (map) → per-agent conductors`, System-IQ rising on validated emissions; every emission also persists into the LAFS ledger.

---

## 3. Advancement Roadmap (staged, non-destructive)

Each stage is independently shippable and testable; nothing rips out working code.

### Stage A — Foundation hardening (low risk)  ✅ COMPLETE (2026-06)
- **A1** ✅ Persist Ω-conductor fabric System-IQ + emissions/growth to Mongo
  (`omega_persistence` `_id="fabric"`). Leading-edge + TRAILING-edge flush (burst-safe);
  restored on `ensure_started`. Verified survives `supervisorctl restart backend`.
- **A2** ✅ Typed settings `core/settings.py` (`pydantic-settings`, cached singleton
  `get_settings()`); Ω-fabric persistence toggle/interval read from it.
- **A3** ✅ Pre-existing: `RequestIdMiddleware` (X-Request-Id correlation) + `AccessLogMiddleware`
  + `core/structured_log.install_json_adapter()` (JSON sink when `LOG_FORMAT=json`). Verified.
- **A4** ✅ Logical route-tree grouping in `core/routes_registry.py` (`ROUTE_GROUPS`,
  `group_of()`, `route_group_summary()` surfaced in the registry report). Physical file
  moves deliberately DEFERRED — 68 route modules cross-import, so grouping is a safe
  classifier rather than a fragile package reshuffle.
- Tests: `backend/tests/test_stage_a_hardening.py` (14) — 14/14 after the burst-flush fix.

### Stage B — Distributed rigor ("Byzantine" done right)  ✅ COMPLETE (2026-06)
- **B1** ✅ REAL N-replica PBFT quorum — `gameforge/prood/quorum.py` (`QuorumConsensus`,
  `Replica`, pre-prepare→prepare→commit, `n>=3f+1` safety, full vote log). API:
  `POST /api/prood/quorum` (+ `faulty` injection), `GET /api/prood/quorum/status`.
  Verified: decides within fault budget, fails safe beyond it.
- **B2** ✅ SagaOrchestrator wired into the real Ship path — `POST /api/gameforge/studio/ship`
  now runs build_web → build_source → git_commit → (push) as a compensating saga
  (auto-rollback in reverse on any failure; `forward_trace` + `compensation_trace` returned).
- **B3** ✅ Durable EventBus→Mongo sink — `gameforge/prood/event_sink.py` mirrors every
  publish (saga.* / build.* / ship.* / quorum.* / iq.grow) into `prood_event_log`;
  `GET /api/prood/logs` streams it (survives restart). Ω-fabric IQ growth publishes `iq.grow`.
- **B4** ✅ Idempotency + optimistic-concurrency primitives — `core/mongo_guard.py`
  (`idempotent_insert` unique-key no-op, `optimistic_update` `_ver` CAS). Applied to Ship
  (`idempotency_key` → duplicate ship suppressed). Broad rollout is incremental per-path.

### Stage C — Cognition depth
- **C1** LAFS auto-`reinforce(deep=True)` on Jury acceptance; nightly online-learning sweeps.
- **C2** Graph belief-propagation multi-hop + posterior-predictive checks surfaced in API.
- **C3** Jeeves retrieval-augmented replies: recall top-EFE LAFS sheets before generating.

### Stage D — Frontend elaboration
- **D1** "What Jeeves Knows" Studio panel (top-EFE ledger sheets + online-learn button).
- **D2** Live fabric/IQ + saga trace stream in Mission Control (websocket or poll).
- **D3** Per-section readiness breakdown (Core Patterns / Key Systems / Frontend / Quality).

### Stage E — Ops & scale
- **E1** Background task runner (APScheduler) for sweeps, cleanup, snapshots.
- **E2** Rate-limit + auth-scope middleware; per-capability health SLOs.
- **E3** Load/chaos tests against resilience circuits.

---

## 3b. Advanced Layers (added 2026-06 — "get this to an advanced level")

These stack ON TOP of A–E, each independently shippable & verified via `testing_agent`.

### Stage F — Retrieval cognition (vector RAG)
- **F1** Embedding-backed canon RAG (replace lexical top-k with real vectors: local
  MiniLM/e5 via `sentence-transformers`, or hash-embeddings fallback) — persisted to a
  `canon_vectors` collection with cosine ANN.
- **F2** Jeeves RAG replies fold top-EFE LAFS sheets AND vector-recalled canon into the prompt.
- **F3** Posterior-predictive "does this contradict canon?" gate on every new artifact.

### Stage G — Secure execution & artifacts
- **G1** Deterministic content-addressed artifact store (sha256 CAS) for builds/vault, GC by refcount.
- **G2** Sandboxed game-code execution smoke-test (resource/time-boxed) before Ship gate.
- **G3** Signed provenance receipts on every Ship (hash-chain already exists — attach to manifest).

### Stage H — Distributed state integrity
- **H1** Roll `core/mongo_guard` optimistic-concurrency out to ALL hot write paths (churn/
  orchestrator/vault) + retry-with-backoff on `conflict`.
- **H2** CRDT-style merge for concurrent KB artifact edits (last-writer-wins → causal merge).
- **H3** Outbox pattern: EventBus publishes are written transactionally with their state change.

### Stage I — Formal rigor & observability depth
- **I1** Runtime invariant contracts (typed pre/post-conditions on saga steps + quorum decisions).
- **I2** Distributed trace spans (correlation-id → per-step timing tree) surfaced in Mission Control.
- **I3** SLO burn-rate alerts per PROOD capability; auto-open a "recovery" room on breach.

### Stage J — Self-improving fabric
- **J1** Ω-fabric System-IQ decay + reinforcement (IQ reflects RECENT validated novelty, not a monotonic counter).
- **J2** Nightly LAFS online-learning sweeps (Wikipedia/free APIs) scheduled by E1's runner.
- **J3** Auto-`reinforce(deep=True)` on Jury acceptance (Stage C1) feeding the fabric's growth signal.

---

## 4. Non-goals (explicit)
- No rewrite that reduces the 99.6% live capability count.
- No deliberately obfuscated/"unmaintainable" code — complexity must buy capability.
- No cyan. No breaking `.env`/metro/ports. Durable state stays in Mongo.

---

## 5. Suggested execution order
`A1 → A3 → B2 → B3 → C1 → C3 → D1 → D2` … then the rest, each verified via `testing_agent`
and reflected in `/api/prood/readiness`.
