# C4 context

Skeleton is the engine and product shell for an AI game builder. People use the Expo web app and the operator CLI. The app foundation client calls the engine HTTP API. External model providers sit behind `skeleton/provider_runtime.py`. MongoDB and Chroma hold durable state. GitHub is the source host. Secrets stay in the process environment and the vault, not on HTTP.

```mermaid
flowchart LR
    person[Builder]
    operator[Operator]
    app[Expo app shell]
    client[skeleton/client SDK]
    engine[Skeleton engine API]
    backend[Codedock backend]
    providers[Model providers]
    mongo[(MongoDB)]
    chroma[(Chroma)]

    person --> app
    operator --> engine
    app --> backend
    client --> engine
    backend --> engine
    engine --> providers
    engine --> mongo
    backend --> mongo
    backend --> chroma
```

The client SDK in progress covers auth, agents, builds, and stream parsing. Projects are published in `docs/architecture/contracts/projects.md` (`skeleton.projects.v1` at `1.0.0`) as the contract for the #4097 router at `/api/v1/projects`. A started build's `execution_id` equals its `build_id`.
