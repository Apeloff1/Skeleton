# Lantern Quay: replay-verified championship seasons

The season engine is an original, offline playable extension of the Lantern Quay game.
A season consists of one to eight distinct authored time-trial courses, all bound to
the same canonical world source. Courses inherit collision, inventory, crafting,
NPC movement, dock delivery and earned-ending rules from the real game engine.
The first completed course unlocks the second, in author-defined order.

## Build and play

The source is the existing `harbor_lantern_quay.json` fixture. Author a season
JSON object with `schema=skeleton.game.harbor.season.v1`, the world's
`source_id`, a `rounds` array of `{id, course}` and strictly descending
`points` keys `gold`, `silver`, `bronze`, `finish`.
Every course is validated against the original world geometry and tick limits.

Use `python -m skeleton.game.gameplay.harbor_crafting_cli season-init
--source <world.json> --season <season.json>` to export an empty portable save.
Play each round with the existing `trial-live` or `play-live` command,
or export a canonical game bundle from `play`. The game must earn every
ordered checkpoint, the correct ending, and the delivery before a round counts.

Append a completed game with `season-append --season-record <record.json>
--bundle <game.json> --expected-season-digest <record_digest>`.
Write the returned JSON to a new file or replace the previous checkpoint only
after the command succeeds. The lease rejects stale writes; no file is modified
by the command. `season-verify --season-record <record.json>` independently
replays every round from source. `season-board --season-records <records.json>`
ranks up to eight independently replayed records; `season-board-verify
--season-board <board.json>` independently recomputes the standings.

## Safety and determinism

No dynamic source execution, network calls, player-identity claims or paid
currency. All input is bounded and duplicate JSON keys are rejected by the
canonical decoder. No round skipping, duplicate game replay, foreign world,
reordered event, forged medal or forged points can earn progress. Season saves
contain complete replay evidence, not only an optimistic score. A board ranks
completed seasons first, then earned rounds, earned points, elapsed ticks and
digest as a deterministic final tie-breaker. A digest proves consistency
against accidental corruption, **not** provenance or authenticity. CLI
exports are portable JSON; external file storage and identity verification
remain the caller's responsibility. Device qualification is not claimed.

Focused acceptance: `pytest -q skeleton/testing/test_harbor_crafting_season.py`.
Full exact-head CI, security, review and release holds remain required.

## Bundled playable two-round season

The repository includes `skeleton/game/gameplay/fixtures/harbor_lantern_quay_season.json`.
Initialize it with `season-init --season <fixture>`. Save the output as a
season record, then use `season-next --season-record <record.json>` to see
the next unlocked authored course and expected CAS digest. Run
`season-live --season-record <record.json>` to play that round using the
existing collision-aware terminal interface. On victory, copy the emitted
`CHECKPOINT` JSON into a game bundle file and append it with
`season-append` and the current record digest. Repeat for the next round.
A completed season returns `status=complete`; attempting to play a
completed record fails closed.

## Choice consequences across the bundled season

The original authored fixture requires `signal` for round one and
`shelter` for round two. Both require real delivery and a legal
player choice. A round-one replay cannot be reused in round two:
the second course independently checks the earned `safe_harbor`
ending. A different ending is a valid standalone game outcome but
**does not** earn the second championship result.
