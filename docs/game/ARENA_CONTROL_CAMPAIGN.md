# Control-Point Campaigns

`python -m skeleton arena-control-campaign demo` plays two original Lantern
Harbor control-point battles. Each battle uses the canonical collision-aware
arena and source-bound capture rules. A verified win earns the stage's
authored reward; a loss or draw earns zero. Two required wins yield the
original campaign's 30 earned currency.

The campaign source has a world ID, player team, required wins and up to four
independently authored control stages. Each stage has a unique control ID
and a bounded reward. A stage must reach a canonical terminal phase before
the campaign advances; partial stages cannot claim rewards. All currency,
wins, losses, draws, stage results, event receipts and save lineage are
recomputed from the complete ordered action journal.

Commands: `new --source-json ...`, `play --source-json ...
--rounds-json ...`, `advance --session-json ... --actions-json ...`,
`verify --session-json ...`, `pack --session-json ...`, and
`unpack --package-json ...`. JSON source, checkpoints and portable
packages are bounded to 2 MiB. All imports replay from immutable source
and reject edited rewards, forged victories and stale source digests.

This is a local offline gameplay/save contract, not authentication, digital
rights certification, network authority or device-release qualification.
