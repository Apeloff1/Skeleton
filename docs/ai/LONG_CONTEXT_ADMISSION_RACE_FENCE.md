# Admission bundle checkpoint race fence

The CPU/RAM/KV cooperative bundle rechecks the generation-fenced KV
window after CPU and memory reservations, after each fair-cycle batch,
and after both claim callbacks. Any change or failed observation
rolls back all recognizable underlying reservations.

The RAM claim receipt must return the exact reservation identity
previously stored by the coordinator. A mismatched identity is a hold,
never an execution lease. Re-observation cannot make external
checkpoint mutation atomic across processes; the actual inference
backend must independently authorize and validate at execution time.

Focused regression tests cover slow reservation callbacks, fair-cycle
partial rollback, checkpoint changes during claim, forged memory
claim identity, and expiry during final observation. No GPU or
M-chip qualification is implied.
