# Cinder Ridge: source-bound multi-episode campaign

Run the bundled original rescue campaign using Python's module entrypoint:
`python -m skeleton.game.gameplay.ridge_rescue.campaign_cli open --output campaign-save.json`.

The campaign consists of two distinct original worlds: First Evacuation and Last
Signal. The first requires an earned protection ending before the second opens.
All transitions use the existing movement, collision, stamina, crafting, market,
raider AI, NPC rescue and consequence engine. No new gameplay rules are invented
in the campaign wrapper. It composes verified replay journals.

Use `inspect --session campaign-save.json` to list legal actions and obtain the
current CAS head. Use `step --session campaign-save.json --expected-head HASH
--action '{"verb":"rest"}' --output next-save.json` to advance. Every output
is create-only; the original save is never overwritten. `interactive` allows
terminal play, with the same deterministic state transitions. `export` creates
a portable source+replay custody envelope, and `verify` replays it before
accepting it. A SHA-256 digest provides integrity, not origin authentication.

Chapters are strictly ordered and cannot be marked complete by claiming a
client-side flag. An ending other than the chapter's required ending leaves
the current chapter terminal and requires an explicit bounded retry. Retries
are capped at three per chapter, recorded in the save and checked on replay.
A lost chapter cannot be silently promoted. CAS rejects stale writers, and
the session verifies its source digest, chapter source identities, each action,
journal hashes, final state, and every earned ending.

Bounded contracts: up to 8 chapters, 96 KB source, 1 MB session, at most
256 actions per chapter, no network dependencies. Offline CLI outputs are
written with restrictive permissions and refuse to overwrite existing files.
This is local integrity custody, not a signed or multi-user authorization layer.
Source-to-runtime-to-save-to-export regression tests live in
`skeleton/testing/test_ridge_rescue_campaign.py`.
