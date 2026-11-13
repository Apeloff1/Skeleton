# NPC interaction calendar — source-bound gameplay hints

The existing offline NPC CLI now supports `--calendar` and
`--verify-calendar`. The calendar derives available and upcoming authored
interactions from a replay-verified NPC save, not from fabricated facts.

```bash
python -m scripts.npc_schedule_cli --schedule lantern_harbor_npc_schedule.json --calendar > calendar.json
python -m scripts.npc_schedule_cli --schedule lantern_harbor_npc_schedule.json --verify-calendar calendar.json
```

Optional `--resume snapshot.json` and `--commands commands.json` let
players preview the calendar after real actions. Each entry contains the
NPC, location, authored time window, earliest possible tick, required
facts, missing facts, grants and current availability. Already-consumed
interactions and expired stops are omitted. The report distinguishes
`available_now`, `available_later` and `missing_facts`.

The first available hint contains only canonical advance/interact commands
that have been replayed through the NPC engine. It reports the resulting
ending, including potentially adverse endings, so it is a neutral hint,
not an automatic game action or promise of a favorable outcome. Future
facts are never predicted as earned. Terminal stories have no future
interaction hints.

Reports are source digest and state digest bound, checksum protected,
replay-verified and capped at 2 MB. At most 128 entries are returned;
`truncated=true` means the report is incomplete. Hashes are integrity
checks, not signatures or ownership proof. The CLI preserves strict
no-follow bounded input reads and duplicate/nonfinite JSON rejection.

```bash
python -m pytest -q skeleton/testing/test_npc_calendar.py
```

Acceptance covers real NPC availability, earned prerequisite transitions,
terminal story holds, bounded truncation, tamper rejection, source mismatch
and CLI export/import. Full exact-head CI remains a separate hold.
