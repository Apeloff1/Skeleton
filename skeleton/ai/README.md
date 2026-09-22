# Canonical AI file tree

`skeleton/ai` is the governed assembly destination for AI implementation code.

The first migration is deliberately non-disruptive: build-plan-relevant code
from current `main`, including Jeeves, is mirrored here using the exact Git
objects already in the repository. Existing imports remain compatibility paths. Non-credential code is held to exact source/destination parity, while credential-bearing destinations must be pure non-owning compatibility facades declared by `machine/ai_file_tree.json`.

## Layout

- `providers/` — provider contract and credential-bearing runtime boundary.
- `runtime/contracts/` — operation/conversation/context contracts.
- `runtime/persistence/` — durable state and recovery.
- `runtime/context/` — context compilation.
- `runtime/retrieval/` — retrieval and grounding.
- `runtime/memory/` — memory.
- `runtime/intelligence/` — admission, verification and execution.
- `runtime/frontier/` — routing, streams and frontier orchestration.
- `runtime/skills/` — tools and skills.
- `agents/jeeves/` — Jeeves reasoning and agent system.
- `build/shift_supervisor/` — planning/scheduling/build-control code promoted
  from the transitional `core/` root.

No compatibility source may be deleted until imports, ownership, focused
tests, rollback evidence, App Assembly, and signed accountability are explicit.
Relocation alone never completes an AIQ task or work package.
