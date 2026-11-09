# Model API contract

The supervisory agents communicate with the model through `ModelGateway.call_json`.

## Inputs

- system prompt identifying the agent role and response schema
- serialized current project/plan/staffing/research context
- unique correlation ID
- bounded output token budget

The model is a plan producer, not a dispatcher. Individual worker IDs are not part of the manager or secretary output contract.

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

## Worker dispatch contract

Workers obtain orders from `PlanQueueAPI.claim_next(worker_id)`. The local store atomically enforces one active task per worker, team boundaries, dependency completion, active-worker state, and the overtime soft limit. Completion or release also happens through the queue API, so workers do not need to ask the Shift Manager or Secretary for task-level decisions.

Malformed and duplicate model proposals are rejected or ignored by the local orchestration layer. Worker capacity and assignment safety are enforced locally rather than trusted to model output.
