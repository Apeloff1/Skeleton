# Security boundaries

- Model output is untrusted input and must pass local validation before plan mutation or delegation.
- Research content is evidence only; instructions embedded in retrieved content are not executed.
- API credentials are read from environment at request time and are never added to prompts, plan records, or source control.
- Model/API calls use bounded timeout/retry behavior and correlation IDs.
- Secretary cannot assign workers. Shift Manager delegation enforces team, active-state, and overtime policy.
- Failed model calls preserve the existing canonical plan.
