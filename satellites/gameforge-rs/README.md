# GameForge-RS v0.3.0 — Ultra-Scale Production System

## Architecture
| Layer | Crate | Responsibility |
|---|---|---|
| Server | gf-server | Axum HTTP, route mounting, middleware stack |
| Core | gf-core | Settings, MongoDB async/sync facades, structured JSON logging, idempotency, event bus |
| Services | gf-services | Ultra infrastructure (LRU cache, connection pool, adaptive backpressure, buffer pool), resilience, observability, security, free-tier cascade, middleware |
| GameForge | gf-gameforge | Ω-fabric, Δ-memory, PBFT quorum, sagas, legions, LAFS, swarm DAG, governance, event sourcing, cognition, media studio, 68 routes, ultra infrastructure |
| FFI | gf-ffi | Diplomat C ABI bindings for Python/JS/WASM consumers |

## Ultra Infrastructure
- **Tiered LRU Cache**: L1 (hot, 60s TTL), L2 (warm, 300s TTL), L3 (persistent Mongo)
- **Connection Pool**: Health-checked, adaptive sizing, proactive replacement
- **Adaptive Backpressure**: Token bucket + load shedding with priority queues
- **Buffer Pool**: Pre-allocated 4KB/64KB/1MB buffers, zero-allocation hot path
- **Request Coalescing**: Thundering herd prevention via deduplication
- **Traffic Shaping**: Token + leaky bucket hybrid for burst/sustained rate control
- **Chaos Tolerance**: Progressive degradation (Normal → Reduced Caching → Shed Background → Stale Reads → Emergency Read-Only)

## Quick Start
```bash
cargo run -p gf-server           # Local
docker-compose up --build        # Docker
make deploy                      # Kubernetes (HPA: 3-20 replicas)
cargo test --workspace           # Tests
```

## Deployment
- Dockerfile: multi-stage build, ~20MB final image
- docker-compose.yml: MongoDB + gf-server
- k8s/deployment.yaml: 3 replicas, liveness/readiness probes, HPA (CPU 70%, memory 80%), resource limits
- .github/workflows/ci.yml: test, clippy, fmt, build, artifact, Docker push

## Doctrine
1. Durable state in Mongo; process is disposable
2. Bounded footprints: delta-memory, ring buffers, sliding windows, pre-allocated buffers
3. Fail-closed security: missing env = closed
4. Byzantine means fault-tolerant: quorum gates novelty
5. Every transition observable on the event bus
6. Rust is the single source of truth; diplomat FFI for foreign consumers
7. Zero-downtime deploys: health checks + graceful shutdown + HPA
8. Chaos tolerance: progressive degradation under failure cascades
