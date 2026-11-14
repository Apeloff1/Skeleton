# Earned supplies in offline combat campaigns

`python -m skeleton combat-supply demo` plays the original Lantern Harbor
campaign using the canonical deterministic turn-combat engine. The authored
source contains a canonical combat campaign and two strictly positive prices:
`medkit` and `ward`. No network service, payment processor, AI provider or
asset download is required.

## Playable CLI

```sh
python -m skeleton combat-supply start --source-json '{"schema_version":"skeleton.combat_campaign_supply.v1","campaign":{...},"prices":{"medkit":8,"ward":10}}'
python -m skeleton combat-supply available --session-json '<saved JSON>'
python -m skeleton combat-supply act --session-json '<saved JSON>' --command-json '{"kind":"fight"}'
python -m skeleton combat-supply act --session-json '<saved JSON>' --command-json '{"kind":"buy","item":"medkit"}'
python -m skeleton combat-supply act --session-json '<saved JSON>' --command-json '{"kind":"use","item":"medkit"}'
python -m skeleton combat-supply finish --session-json '<saved JSON>'
python -m skeleton combat-supply verify --session-json '<saved JSON>'
python -m skeleton combat-supply pack --session-json '<saved JSON>'
python -m skeleton combat-supply unpack --package-json '<portable JSON>'
```

`fight` settles exactly one authored encounter with canonical combat.
Only verified victories award source-defined currency. A medkit costs earned
currency and restores at most four HP without exceeding the original hero
maximum. A ward is consumed on the next fight, adding two defense for that
encounter only. Both have three-item inventory caps; no-op healing, overspend,
duplicate keys, invalid commands, unknown schema, replay mismatch and
oversized output fail closed. A loss or draw ends the campaign; continuing a
terminal save is rejected.

The source digest is frozen at creation. Each save contains the full ordered
command journal, nested canonical combat receipts, state digest and parent
save lineage. Restoring re-executes every command and combat encounter from
authored source rather than trusting client state. Portable packages include
a manifest and integrity digest; **these are not signatures or authorization
proofs**. A different authored source requires a new playthrough.

The canonical source editor can modify the underlying campaign before a
supply session starts. A separate supply-price editor adds optimistic
source-digest checks and replay-derived previews; it cannot rewrite an
already saved campaign without invalidating the source binding.

Regression tests: `python -m pytest skeleton/testing/test_combat_campaign_supply.py`.
Full exact-head CI and device/release qualification remain mandatory.
