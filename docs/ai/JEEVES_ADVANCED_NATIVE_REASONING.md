# Jeeves native desktop — bounded advanced reasoning

Jeeves now exposes two actual planner topologies for its already-installed
local GGUF. They use the **same** `NativeJeevesRuntime` and
`StrictJeevesAgentRuntime`, the existing `ExecutionSpine` SQLite authority,
and exactly the source/tool grants approved at startup. No second model,
hosted API, shell permission, hidden memory store or automatic tool grant is
created by selecting a reasoning profile.

## Choose a profile

The desktop **Reasoning profile** control offers `guarded` and
`advanced`. The interactive GUI defaults to `advanced`. Source-only API
users continue defaulting to `guarded` unless they explicitly select
the advanced policy.

### Guarded

The existing conservative native agent behavior: at most four plan steps,
zero replans, no extra verification call by default, fail on unresolved
claims, no memory staging and no automatic tool grants. This is useful
for low-memory laptops, narrow tasks and small models.

### Advanced

Advanced mode requires at least **4 operator-admitted steps** and
**6 operator-admitted native model calls**. It enables, through the
already established `AgentConfig`:

- Up to 32 individual plan steps, never exceeding the user-approved
  `maximum_steps`.
- Up to 2 bounded replans when the model-call budget supports them.
- A bounded grounding repair when the model-call budget reaches 8.
- Independent model verification requested for final reasoning.
- Read-only evidence verification requested only when an operator-signed
  source tool is already enabled and the model-call budget supports it.
- Explicit zero temperature for deterministic planning envelopes.
- Fail on unresolved evidence, with no hidden memory-candidate promotion,
  success-episode staging or relaxed claim grounding.

Each prompt/planner/step/verifier/final call remains below the **actual
installed native model's output-token ceiling**. The existing
`RunInputs.Budget` continues to bind the total model-call/step/tool/time
budgets and the worker's isolated native inference and SQLite receipt
boundaries.

The desktop host and private binary client check the exact
`reasoning_profile`, policy schema, immutable permission fields,
run ID, source/model digest and UTF-8 answer hash before displaying a
success receipt. An unsupported profile, insufficient budget, wrong source,
unexpected tool call or unverified final answer cannot silently downgrade
to the simpler profile or claim success.

## Difference between requested and executed verification

The profile receipt says **model verification requested**; it does not
automatically assert that a real GGUF verified the answer. The strict
runtime's own authoritative success, usage and grounding result remain
responsible for model-level evidence. The desktop never converts a source
test or a compiler pass into real model/device qualification.

These controls improve the planner's available operational trajectory,
not the physical inference hardware. Native model licensing,
first Windows 11/WSL2 laptop run, cold SQLite replay under a live source
guard, device pressure/cancellation and exact-head release/security checks
must still be independently completed. The model does not run external
tools or write files unless a separate, earlier explicit and verified
source authorization exists; even that source tool is read-only.
