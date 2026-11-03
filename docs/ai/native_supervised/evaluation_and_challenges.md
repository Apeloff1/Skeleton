# Independent 768-case native AI evaluation

The challenge catalog includes exactly 32 domains with 24 original
cases per domain. Eight operational/security domains are treated as
critical and include traversal decisions, read-only allowlists,
same-owner access, synthetic redaction, job status, safe retry,
evidence comparison and source provenance.

Each case is a structured record with domain, ordinal, arguments,
prompt, expected answer, severity, rights and stable SHA. A separate
oracle recomputes prompt and expected answer from arguments.
Altered answers, malformed identifiers, missing files, wrong
severity or changed source provenance fail case admission.

Challenges are not added to the model's tokenizer fitting or SGD.
The evaluator loads a hash-pinned checkpoint into the real native
runtime and submits the prompt to NativeChatEngine. It compares the
generated answer with the fixed expected answer, and preserves the
actual model/tokenizer/replay receipt identity, output digest,
finish reason, token counts and request timing.

A 24-case segment is not a 768-case run. Segments may be combined only
when consecutive, nonoverlapping, source-bound and model-identical.
The full result retains per-domain scores and critical failure counts.
Source-complete execution is not inferred from a fixture count.

An independent replay can rerun the same cases from the pinned
checkpoint, compare actual content/receipt identities and record
mismatches. Measured wall time is deliberately excluded from stable
replay equivalence.

The candidate and champion must be evaluated against the exact same
case IDs and source digest. Any critical regression is reported as
a separate hold and cannot be balanced away by easy-task improvements.
Even zero critical regressions plus positive scores do not establish
broad capability or automatically authorize release.
