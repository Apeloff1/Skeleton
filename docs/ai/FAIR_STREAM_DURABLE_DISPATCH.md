# Fail-closed durable fair-stream dispatch

`DurableFairStreamSession` connects the canonical deterministic fair-stream
scheduler, HMAC-authenticated custody, transactional SQLite CAS and an
**independent trusted high-watermark**. It returns dispatch permits only after
both the SQLite transition and external generation/digest CAS succeed.

A permit is a committed scheduling intent, not proof of GPU memory allocation,
model execution, output delivery, power/thermal stability or device qualification.
Only the trusted execution owner can issue a completion receipt after durable
completion intent, and pending leases are never silently reexecuted on restart.

The app must supply a symlink-safe private SQLite connection, independent
durable high-watermark implementation, separate secret custody, real OS probes,
bounded disk reserve, backend enforcement and an outbox for result completion.
The module intentionally does not invent those components. An outage between
SQLite COMMIT and independent anchor advancement quarantines the session for
explicit operator recovery. A corrupt/missing external anchor also quarantines.
Unknown and operator/simulated resource measurements cannot dispatch.

Canonical tests use a clearly labelled in-memory simulated anchor; they do
not establish crash-atomic durability of an actual external key store, nor
Apple Silicon/Metal, NVIDIA, ROCm or Windows device qualification.
