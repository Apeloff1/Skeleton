# Source parity matrix — 2026-09-13

| Capability | Source | Canonical target | Status | Next action |
|---|---|---|---|---|
| Tiered cache | gameforge-rs | `skeleton/kernel` | candidate | contract/test parity |
| Connection pool | gameforge-rs | `skeleton/kernel` | candidate | health + exhaustion parity |
| Adaptive backpressure | gameforge-rs | `skeleton/kernel` | candidate | saturation/fail-closed tests |
| Buffer pool | gameforge-rs | `skeleton/kernel` | candidate | ownership/reuse contract |
| Request coalescing | gameforge-rs | `skeleton/kernel` | candidate | duplicate request/idempotency tests |
| Chaos tolerance | gameforge-rs | `skeleton/services` | candidate | degradation-state parity |
| PBFT/quorum | gameforge-rs | `skeleton/kernel/court.py` | candidate | safety/liveness comparison |
| Event bus/idempotency | gameforge-rs | runtime/services | characterize | extract invariant contract |
| Jeeves system laws | Prood/Tutolage | `skeleton/ai`, `skeleton/learning` | candidate | normalize provider-neutral laws |
| Text-to-NPC | Prood/Tutolage | `skeleton/game` | candidate | interface + deterministic fixture |
| Text-to-game-logic | Prood/Tutolage | `skeleton/game` | candidate | interface + validation fixture |
| Immersive tutor/ZPD | Prood/Tutolage | `skeleton/learning` | candidate | contract extraction |
| Chroma RAG | Prood/Tutolage | `skeleton/memory` | adapter | isolate vector-store dependency |
| Mongo service | Prood/Tutolage | `services` | adapter | keep persistence outside kernel |
| FastAPI routes | Prood/Tutolage | services | reject wholesale | preserve domain contracts only |
| Expo/Zustand frontend | Prood/Tutolage | apps/cockpit | defer | canonical frontend wins |
| Axum routes | gameforge-rs | services | reject wholesale | preserve Rust domain semantics only |
| C ABI | gameforge-rs | adapters | characterize | wait for stable contracts |
| C# Zaibatsu gate | gameforge-middleware | sibling adapter | characterize | document external contract |
| 3D ECS cockpit | hyperforge-cockpit-sota | apps/cockpit | defer | mine reusable domain types only |

## Rule

`candidate` does not mean copied. Promotion requires the promotion gates and a source-backed contract test. Existing Skeleton implementations are preferred when behavior is already equivalent.
