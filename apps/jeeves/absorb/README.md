# Jeeves Absorb Engine

This directory contains the orthogonal absorption plane for Jeeves. It is intentionally isolated from live inference so ingestion pressure cannot degrade request latency.

Core responsibilities:
- durable observation intake;
- deterministic fingerprinting and deduplication;
- compute-normalized priority scoring;
- adversarial validation and quarantine;
- tiered knowledge promotion;
- immutable snapshot manifests for serving.

The initial implementation is dependency-light so it can be integrated with the existing runtime incrementally. Production adapters can replace the in-memory queue/journal interfaces with Kafka, NATS JetStream, Redis Streams, Postgres, object storage, or the repository's canonical infrastructure without changing the promotion contract.
