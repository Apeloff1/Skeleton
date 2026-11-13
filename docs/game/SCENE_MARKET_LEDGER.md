# Offline scene market economic provenance

The canonical `scene-market` command exposes replay-derived economic
accounting for original playable markets. A ledger is **read-only evidence**,
not a new wallet, a bank balance, an author signature or a release certificate.

Run `python -m skeleton scene-market demo` to obtain a complete canonical
session. Supply that JSON to `python -m skeleton scene-market ledger
--session-json '<session>'` to inspect every earned coin, purchase, craft,
delivery, resulting inventory and reputation change. The action digest and
canonical journal receipt bind each row to the original replay.

`scene-market ledger-export --session-json '<session>'` returns a portable
bundle with the canonical session and the audit witness. Use `scene-market
ledger-import --bundle-json '<bundle>'` to verify and recover the canonical
session. The import recomputes the ledger from the source and journal; it
rejects forged totals even if an attacker recomputes an ordinary checksum.
Checksums detect accidental changes but do not authenticate an author.

Every replay step enforces the original market rules: pickups are the only
coin mint, finite offers spend earned credits, crafting conserves inputs and
outputs according to authored recipes, deliveries spend goods once and
award authored reputation. All commands fail closed on unknown versions,
malformed JSON, oversized inputs, mismatched receipts or forged state.

Validation: `python -m pytest skeleton/testing/test_scene_market.py
skeleton/testing/test_scene_market_ledger.py`. Device and release acceptance
remain separate, mandatory exact-head gates.
