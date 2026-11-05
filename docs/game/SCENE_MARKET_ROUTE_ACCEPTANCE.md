# Market route acceptance: source to playable delivery

`python -m skeleton scene-market-route-accept demo` composes the market
route solver, player-facing board, canonical market replay, source-bound
checkpoint reconciliation, economic conservation ledger, interactive play,
transactional editor preview and portable export/import.

For an authored checkpoint run
`python -m skeleton scene-market-route-accept audit --session-json JSON`.
To independently recompute the receipt use
`python -m skeleton scene-market-route-accept verify --session-json JSON
--report-json JSON`. The report includes exact source, checkpoint, terminal,
route, ledger, board, reconciliation, integrated acceptance and export digests.

The route must actually win within bounded search, otherwise the CLI fails
closed. `--allow-inconclusive` returns an explicitly unqualified report with
no victory claim. `--skip-editor` omits editor evidence while retaining
canonical gameplay, save, economic and portable delivery validation.

This is single-source offline functional acceptance, **not** consumer laptop
qualification, trusted provenance, rights certification, or release approval.
An unkeyed digest is an integrity checksum, not an authentication signature.
