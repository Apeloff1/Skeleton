# Market Fork Authoring and Delivery Acceptance

The creator can edit previewed player alternatives without mutating a
source-bound game save. `python -m skeleton scene-market-fork-author demo`
renames the winning original route and returns a deterministic edit receipt.

`scene-market-fork-author edit --report-json '<preview>' --edits-json
'<operations>'` accepts bounded add, replace, remove and rename operations.
Every operation is checked before publication; conflicting IDs, empty plans,
unknown candidates and excessive batches fail the entire transaction. The
result contains the unchanged original preview, the validated edit sequence,
a fully replayed preview and integrity digests. `verify --receipt-json`
replays the editor transaction and checks the exact result.

`python -m skeleton scene-market-fork-accept demo` proves an end-to-end
original victory from authored market source through replayed player choice,
earned currency, finite stock, crafting, delivery, canonical game save,
portable export/import and an independently recomputed economic ledger.
`scene-market-fork-accept accept --report-json '<preview>' --candidate-id
'<winning-id>'` publishes an offline acceptance witness. `verify
--witness-json '<witness>'` reconstructs the same game from the included
source-bound preview. Blocked or non-winning choices never qualify.

These checks are offline functional evidence, not external authentication,
real device qualification or consumer release approval. Both tools return
machine-readable JSON on stdout and fail closed with JSON error on stderr.
