# Original offline combat campaign

The campaign owner is skeleton/game/gameplay/combat_campaign.py and the
canonical turn engine remains skeleton/game/gameplay/turn_combat.py.
Run python -m skeleton combat-campaign demo for a real original two-encounter
Lantern Harbor patrol, deterministic opponents, persistent hero health and
bounded victory-only currency rewards. Run combat-campaign simulate with
--source-json to use authored encounters, advance with --session-json for
one encounter, resume for remaining encounters, and verify for a full replay.

Every authored encounter uses the versioned canonical combat schema.
All hero stats except current HP must remain stable; HP carries forward and
never heals magically between encounters. Source digest, combat turn journal,
reward ledger, parent save lineage and replayed state must all agree.
Only verified canonical victory grants rewards; loss/draw stops the campaign.
No network, provider, native engine, third-party media or signature is claimed.
All currency and turns are bounded, and a session is never trusted as an
authoritative game economy grant without separate app authorization.

Test: python -m pytest -q skeleton/testing/test_combat_campaign.py
