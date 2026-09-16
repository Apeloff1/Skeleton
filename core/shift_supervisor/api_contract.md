# Model API contract

The supervisory agents communicate with the model through `ModelGateway.call_json`.

## Inputs

- system prompt identifying the agent role and response schema
- serialized current project/plan/staffing/research context
- unique correlation ID
- bounded output token budget

## Manager expected response

```json
{
  "summary": "...",
  "tasks": [
    {
      "title": "...",
      "description": "...",
      "priority": 80,
      "target_team": "night",
      "rationale": "...",
      "research_refs": ["..."],
      "expected_output": "...",
      "validation": ["..."],
      "dependencies": ["..."]
    }
  ],
  "delegation": [
    {
      "task_id_or_title": "...",
      "worker_id": "...",
      "reason": "..."
    }
  ]
}
```

## Secretary expected response

```json
{
  "summary": "...",
  "tasks": [
    {
      "title": "...",
      "description": "...",
      "priority": 70,
      "target_team": "idle",
      "rationale": "...",
      "research_refs": ["..."],
      "expected_output": "...",
      "validation": ["..."],
      "dependencies": ["..."]
    }
  ]
}
```

Malformed, duplicate, cross-team, blocked-worker, and excess-overtime proposals are rejected or ignored by the local orchestration layer rather than trusted solely because they came from a model.
