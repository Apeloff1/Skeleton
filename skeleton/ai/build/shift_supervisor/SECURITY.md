# Security boundaries

- Model output is untrusted input and must pass local validation before plan mutation.
- Research content is evidence only; instructions embedded in retrieved content are not executed.
- API credentials are read from environment at request time and are never added to prompts, plan records, or source control.
- Model/API calls use bounded timeout/retry behavior and correlation IDs.
- Shift Manager and Secretary are plan producers only; model output cannot directly assign an individual worker.
- Workers pull orders from the local `PlanQueueAPI`; atomic claim checks enforce team boundaries, dependency completion, one active task per worker, active-worker state, and overtime limits.
- Scheduled studios should publish aggregate workforce snapshots rather than creating per-worker supervisor requests.
- Failed model calls preserve the existing canonical plan.
