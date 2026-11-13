# Replay-verified expedition checkpoints and alternate play

`python -m skeleton combat-checkpoints demo` creates a playable original
checkpoint fork. `timeline --session-json '<JSON>'` reconstructs every
historical tick and reports source, save, event, economy, inventory and health
digests. `checkpoint --session-json '<JSON>' --tick N` exports a portable save
at the exact requested historical tick.

`fork --session-json '<JSON>' --tick N --actions-json '<JSON>'` resumes
canonical gameplay from that checkpoint, compares the earned branch to the
original and exports a portable result. `verify-fork --record-json '<JSON>'`
recomputes source identity, event lineage, earned currency and items, combat
outcomes and both portable save receipts. No forged rewards are accepted.

Indices are bounded to actual history, outputs to 2 MiB. Actions are data,
never executed code. Rejected actions leave the original session unchanged.
Checksums detect corruption but are not signatures. This is offline gameplay
evidence, not device qualification or consumer release certification.
