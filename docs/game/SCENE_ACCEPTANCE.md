# Offline Scene Acceptance — source to replay to export

Run `python -m skeleton scene-accept check --demo` to produce a deterministic
acceptance report for the original Lantern Hollow playable vertical. For authored
worlds use `check --world-json '<JSON>'`; for a trusted checkpoint use
`check --session-json '<JSON>'`. The same command is available as
`python -m skeleton.game.gameplay.scene_acceptance`.

A **passed** result requires a complete bounded scene reachability audit,
no unobserved authored scenes, a real victory witness, and a second independently
replayed victory route. Every observed ending is replayed by the canonical
scene runtime, verified from its event journal, exported as a portable offline
save, imported again and compared for exact equality. The report binds all
proofs to the normalized source digest and exact starting checkpoint. The
`report_digest` is a deterministic checksum, **not a signature**.

Use `python -m skeleton scene-accept verify --report-json '<JSON>'` to
recompute all evidence. Edited status, proof, source, history, budget, digest
or claimed release readiness is rejected. Verification does not require a
network connection, model provider, filesystem access or untrusted code.

Exit codes: 0 means passed; 1 means failed because victory or complete scene
coverage was not demonstrated; 3 means the bounded search was inconclusive;
2 means invalid input, invalid replay or tampered evidence. Search budgets
default to 1024 states and 64 actions and are capped at 4096/512. Reports
are capped at 2 MiB. Budget exhaustion is never silently reported as
unreachable. Existing saves remain immutable when acceptance fails.

Acceptance covers **this offline scene gameplay vertical only**. It does not
certify installed devices, rights, real-time rendering, security, GitHub CI,
or a consumer release. All repository exact-head release gates remain required.
