# Frontier Architecture Contract

## Layering

Dependencies point inward/downward. Core packages must not import cockpit or domain packs.

```text
apps / cockpit
       |
    services
       |
 forge / game / learning
       |
 intelligence / swarm
       |
 memory
       |
 runtime
       |
 kernel
```

## Canonical contracts

### Agent

```python
class Agent:
    name: str
    capabilities: set[str]

    async def run(self, task, context=None): ...
```

Implementations may differ internally, but callers must depend on the contract rather than vendor/model-specific classes.

### Memory

```python
class MemoryStore:
    async def put(self, item): ...
    async def search(self, query, *, limit=10, filters=None): ...
    async def delete(self, item_id): ...
```

### Event

All cross-subsystem state changes should be representable as typed domain events with correlation and causation identifiers.

### Capability

Agents, services and tools expose explicit capabilities. Capability checks happen before side effects.

### Provenance

Generated artifacts retain source, model/provider, prompt/task identity where available, timestamps, and validation state.

## Model/provider neutrality

The frontier build must not hard-code one model provider into the kernel. Provider adapters belong below the intelligence contract. Model routing, fallback and evaluation are runtime policy.

## Data boundaries

- operational state: database adapters;
- vector state: memory adapters;
- static knowledge: versioned knowledge packs;
- large assets: LFS/artifact storage;
- secrets: runtime secret provider;
- telemetry: observability backend.

## Runtime profiles

`minimal` — kernel + runtime only.  
`ai` — intelligence + memory + tools.  
`game` — AI + game + simulation.  
`learning` — AI + memory + tutoring.  
`studio` — all application planes + cockpit.

The default developer environment should remain lightweight; optional profiles prevent the full multi-GB asset plane from becoming a prerequisite for ordinary source development.
