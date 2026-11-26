# Cinder Ridge executable product acceptance matrix

The acceptance matrix executes six independent product contracts from original
game source through the actual runtime, deterministic saves, replay-verified
exports and editing. It is not a simulated CI result or an administrative
release certificate.

```bash
python -m skeleton.game.gameplay.ridge_rescue.qualification_cli
python -m skeleton.game.gameplay.ridge_rescue.qualification_cli --fail-fast
python -m skeleton.game.gameplay.ridge_rescue.qualification_cli --output /tmp/ridge-acceptance.json
```

The runner checks world/package integrity, both choice-dependent routebook
endings, a real two-chapter campaign, replay-verified map editing, tactical
turn preview/commit, and the mission-event DAG. Each check reports a source
or journal digest and the actually observed result. An exception records a
failed check; the CLI returns a nonzero exit status if any check fails.
`--fail-fast` stops at the first error and cannot report an incomplete
matrix as passed.

This only qualifies the in-process game contracts **when actually executed**.
Authoring this runner is not proof that it passed. Exact-head GitHub CI,
security, review, malware, artifact, dependency and device release holds
remain independent and mandatory.
