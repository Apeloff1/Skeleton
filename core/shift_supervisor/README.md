# Shift Supervisor

`core.shift_supervisor` coordinates the Night Shift and Idle Shift worker teams.

## Runtime model/API configuration

Both `SMBShiftManager` and `SecretaryBot` call the same `ModelGateway`. Configuration is read at request time:

- `OPENAI_API_KEY` — required default API credential.
- `SHIFT_MODEL_API_URL` — optional OpenAI-compatible endpoint override; defaults to `https://api.openai.com/v1/chat/completions`.
- `SHIFT_MODEL_NAME` — optional model override; defaults to `gpt-5.6`.

The API key is never stored in plan data or committed to the repository.

## Cadence

- Secretary: every 15 minutes. Expands the canonical plan with concrete validated workload.
- Shift Manager: every 30 minutes. Rebuilds priorities/delegation using project context, research, staffing and overtime.

Both cadences use a shared store. The Secretary cannot directly assign workers; the Shift Manager owns delegation.

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

Use `SMBShiftManager.clock_in`, `heartbeat`, and `clock_out`. Heartbeats record worker state and the current task. Elapsed time past `normal_shift_minutes` becomes overtime, and task IDs being worked during overtime are retained for attribution.

## Research

`ResearchBroker` isolates sources so one failed provider does not erase other research. Source adapters receive project context and yield dictionaries. The Shift Manager receives their merged records on each 30-minute plan refresh.
