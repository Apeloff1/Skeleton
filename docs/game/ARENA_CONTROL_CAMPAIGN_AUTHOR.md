# Transactional Control-Point Campaign Authoring

`python -m skeleton arena-control-campaign-author demo` edits the original
two-stage Lantern Harbor beacon patrol and replays both real battles. It
changes the first stage's earned reward to 12 and the campaign win threshold
to one, producing a deterministic 32-currency preview.

`edit --source-json ... --operations-json ... --expected-digest ...
--rounds-json ...` accepts a source-bound atomic transaction. Supported
operations are `set-stage-reward`, `set-required-wins`, and
`edit-stage-control`. The latter reuses the canonical per-stage editor
for zone movement, zone points, action budget and score targets, with its
own nested replay-verified preview. A campaign preview must finish every
stage, so untested reward changes cannot be accepted as completed authoring.

`verify --source-json ... --receipt-json ...` independently reapplies
all edits, recompiles the campaign, reruns each canonical tactical stage,
and compares child edit receipts, action journals, earned rewards and save
lineage. Stale digests, no-op edits, unknown stage IDs, invalid nested
source, unplayable previews and forged receipts fail closed. The input
source is not mutated.

Receipts prove deterministic local integrity only, not author identity,
license rights, network multiplayer authority or consumer-device readiness.
