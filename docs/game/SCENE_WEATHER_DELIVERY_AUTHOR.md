# Weather caravan editor — source-bound production workflow

`python -m skeleton weather-deliveries-author demo` changes an authored
delivery reward using an expected canonical source digest, validates the
entire weather/delivery source, runs bounded canonical route search, and
produces a replay-verifiable portable game preview when a route is found.

```sh
python -m skeleton weather-deliveries-author edit --source-json '<source>' --operations-json '<edits>' --expected-digest '<sha256>'
python -m skeleton weather-deliveries-author verify --source-json '<original>' --receipt-json '<receipt>'
```

Operations: `add-delivery`, `remove-delivery`, `set-deadline`,
`set-reward`, `set-destination`, `set-item`, `set-requires`.
Transactions are atomic, reject stale leases and no-ops, and compile through
the canonical weather, scene and delivery validators. A preview that cannot
be proven within 128 states/depth 16 is **inconclusive** or **unreachable**,
never silently declared playable. All receipt fields, nested game state,
reward and route witness are reconstructed during verification.

The source digest and receipt detect drift; they do not grant permission or
establish authorship. Consumer, device and CI release gates remain in force.
