# Cooperative market route and playable delivery acceptance

The party route tool searches legal turns through the canonical party
arbitration and market economy. It does not grant goods, credits, crafting
rights or delivery rewards. The player whose turn it is must hold the role
required for every trade, craft, delivery or tile action. Passing changes
only turn ownership and cannot mint currency.

## Player commands

`python -m skeleton scene-market-party-route demo` replays the original
cooperative victory and returns a checksummed witness with source digest,
initial save digest, terminal state/save digests, portable bundle checksum
and the exact player/turn sequence. The hint is never trusted: it must
replay from the supplied checkpoint to a canonical earned victory.

`python -m skeleton scene-market-party-route solve --session-json '<json>' --max-nodes 256 --max-depth 48`
searches a user checkpoint. The report is `proven_win` only when the
canonical reducer accepts every turn and the resulting replay is a win.
An exhausted node, frontier or depth budget is `inconclusive`. The solver
does not assert that a game is impossible or that its route is globally
optimal. `verify --session-json '<json>' --report-json '<json>'`
recomputes the report and rejects altered or stale witnesses.

`python -m skeleton scene-market-party-accept demo` exercises the
complete original cooperative campaign through source normalization,
pre-restart play, portable checkpoint export/import, interactive JSON
line input, verified checkpoint events, final replay equality, route
witness and portable final export/import. For authored games, use
`accept --source-json '<json>' --turns-json '<json>' [--split N]`.
The authored player IDs in turns are independently checked against the
canonical turn scheduler. The interactive engine consumes the action
part only, assigning the current player itself.

## Trust and boundedness

This is an offline integrity and deterministic-playability check, not
authentication, hardware certification or a release approval. SHA
digests and checksums detect accidental or adversarial changes only
when compared against an independently trusted source digest. The
route solver has explicit node, depth, candidate and output bounds;
it never silently treats a bounded miss as an unwinnable world.
All checkpoints and exported bundles are replay-verified before
being used. Invalid actions, source drift, incorrect actor ownership,
corrupted save lineage and fabricated victory reports fail closed.
