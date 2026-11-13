# Real AI operational control primitives

Ten local fail-closed controllers coordinate model epochs, request idempotency,
deadlines/retries, explicit HMAC memory consent, credit-limited streaming,
pinned local routing, operator-controlled model rollouts, evaluation counts,
recovery ordering, and tool intent custody. None starts an external process,
makes a hosted-model call, or grants shell/network privileges.

**Authority boundaries:** The model epoch fence is process-local; the
canonical durable SQLite store remains the final replay authority.
Release evidence must be independently fetched from GitHub and tied to exact
final commit SHA. Consent HMAC secret custody remains an operator
responsibility. Rollouts require independent evidence and explicit approval.

Controllers are intended for integration with existing GGUF/native product
code only after focused and native-E2E verification. They do not replace the
existing serving engine, installer, transactional database or Linux process
fencing.
