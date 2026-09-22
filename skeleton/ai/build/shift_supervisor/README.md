# Shift Supervisor

`core.shift_supervisor` coordinates the Night Shift and Idle Shift worker teams without turning the supervisor into a per-worker dispatch bottleneck.

## Runtime model/API configuration

Both `SMBShiftManager` and `SecretaryBot` call the same `ModelGateway`. Configuration is read at request time:

- `OPENAI_API_KEY` — required default API credential.
- `SHIFT_MODEL_API_URL` — optional OpenAI-compatible endpoint override; defaults to `https://api.openai.com/v1/chat/completions`.
- `SHIFT_MODEL_NAME` — optional model override; defaults to `gpt-5.6`.

The API key is never stored in plan data or committed to the repository.

## Cadence

- Secretary: every 15 minutes. Expands the canonical plan with concrete validated workload.
- Shift Manager: every 30 minutes. Refreshes priorities using project context, research, aggregate staffing, blocked work, and overtime pressure.

Both agents are **plan producers only**. Neither agent assigns work to an individual bot.

## Dispatch architecture

Night and Idle workers pull orders from the canonical plan through `PlanQueueAPI` instead of asking the Shift Manager or Secretary what to do. This keeps a large fleet from swarming either supervisory agent.

The queue enforces the dispatch invariants locally and atomically:

- one active task per worker;
- exact team match (`night` work goes only to Night workers and `idle` work only to Idle workers);
- dependencies must already be complete;
- offline and blocked workers cannot claim work;
- workers at the overtime soft limit cannot claim additional work;
- concurrent claims cannot double-assign the same plan item;
- unfinished work can be released back to the queue without contacting a supervisor.

The durable worker ledger can still track the full workforce. Model planning receives aggregate team capacity plus a bounded attention list rather than a thousand individual worker records on every refresh.

```python
from core.shift_supervisor.plan_api import PlanQueueAPI

queue = PlanQueueAPI(store, overtime_soft_limit_minutes=120)
order = queue.claim_next("night-builder-17")
if order is not None:
    # Execute the plan item, then close it locally.
    queue.complete("night-builder-17", order["id"])
```

## Minimal integration

```python
from core.shift_supervisor.runtime import build_supervisor

scheduler = build_supervisor(
    project_context_supplier=lambda: {
        "repository": "Apeloff1/Skeleton",
        "backlog": [],
        "recent_failures": [],
    },
    research_sources={
        # Plug the repo's GitHub/search/telemetry adapters in here.
        # "github": github_research_adapter,
        # "web": web_research_adapter,
    },
)

scheduler.run_forever()
```

For service deployments, run `SupervisorScheduler` under the repository's normal process/service supervisor rather than spawning it from import-time code.

## Worker tracking

Use `SMBShiftManager.clock_in`, `heartbeat`, and `clock_out` or the narrow `WorkerControlAPI` adapter for status reporting. Heartbeats record worker state and the current task. Elapsed time past `normal_shift_minutes` becomes overtime, and task IDs being worked during overtime are retained for attribution. Scheduled studio workflows should prefer their existing aggregated workforce snapshots so hundreds of workers do not create supervisory request fan-in.

## Research

`ResearchBroker` isolates sources so one failed provider does not erase other research. Source adapters receive project context and yield dictionaries. The Shift Manager receives their merged records on each 30-minute plan refresh.
