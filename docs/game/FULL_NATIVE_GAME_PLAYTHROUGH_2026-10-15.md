# Full native game playthroughs and expanded Jeeves training horizons (2026-10-15)

## Actual milestones

1. Removed the former **256-episode training-policy ceiling** as a fixed maximum. Both Jeeves package owners now default to 1,024 episodes and accept an explicitly configured **8,192 per policy**. Cumulative fork lineage permits up to 65,536 recorded episodes and 16,777,216 update steps, still subject to the *existing* snapshot byte/structural, state-table, per-policy update, imitation, and trace limits. A large configured ceiling is **not** a claim the maximum was executed or that every policy can fit into an 8 MiB snapshot. Use \`--max-episodes\` for the local training CLI and \`--max-updates\` as needed.
2. Preserved 4,096-step bounded *learning* episodes, but introduced **explicit native-core continuation**: \`EmulatorEnvironment.continue_playthrough()\` rolls a completed logical window forward without \`retro_reset\`, native core replacement, content change or transition chain loss.
3. Added a compressed 1–4-controller input program with up to **100,000,000 native input steps** across these windows. Each instruction uses \`repeat\`; raw ports use the native host's bounded canonical controller vectors.
4. Added wall-clock-bounded execution in increments of up to 7,200 seconds per **foreground operator invocation**, with explicit \`--resume\` from verified native savestate. No background run is claimed.
5. Added durable sha256-linked evidence checkpoints, controller/frame/audio digest samples, native-run counters, explicit pause/cancellation status and receipt files with strict finite storage bounds.
6. Added an offline receipt auditor that checks input-plan/environment identity, contiguous absolute cursors, checkpoint consistency and receipt hash continuity.
7. Added game-specific completion predicates using exact native frame sha256 or 1–8 bytes of approved libretro-exposed memory. A matched watch is recorded as \`completion_rule_matched\`, **not** as certified game success. An exhausted scripted tape is \`input_exhausted\`, **not** victory.
8. Implemented both \`skeleton/jeeves/\` and \`skeleton/ai/agents/jeeves/\` owners plus a standalone operator CLI. No ROMs, core binaries, BIOS, source-downloaded games or fabricated native output are bundled.

## Example original/homebrew input plan

Save the following as \`/srv/homebrew/long-playthrough.json\`:

\`\`\`json
{
  "schema_version": "skeleton.game.native_playthrough_plan.v1",
  "seed": 117,
  "max_total_steps": 100000000,
  "completion": null,
  "instructions": [
    {"action": "start", "repeat": 1},
    {"action": "right", "repeat": 25000},
    {"action": "a_right", "repeat": 10000},
    {"action": "idle", "repeat": 6000}
  ]
}
\`\`\`

The above is deliberately *not* a known complete game solution. It demonstrates the long-session execution protocol, not gameplay mastery. Every action consumes one native step; \`--frames-per-step\` controls how many actual \`retro_run\` callbacks run in a step. Total actual native frames can therefore be much larger than the number of input steps.

For an actual game-specific end detector replace \`"completion": null\` with an **operator-verified** condition such as:

\`\`\`json
{
  "kind": "memory_equals",
  "region": 2,
  "offset": 1234,
  "expected_hex": "01",
  "poll_every": 60
}
\`\`\`

The region/offset above are illustrative only: use the **verified** location from the legally approved game and installed core, not this placeholder. Or use \`{"kind":"frame_sha256","sha256":"<verified actual lowercase 64-char frame digest>","poll_every":1}\`. Frame equality and RAM observations can represent menus, loading, or transient scenes; neither intrinsically proves an ending or credits.

Run explicitly with an approved local libretro registry and lawful homebrew:

\`\`\`bash
python3 scripts/run_game_playthrough.py \
  --registry /srv/skeleton-emulators/cores.json \
  --target nes --core fceumm \
  --source /srv/homebrew/my-game.nes \
  --plan /srv/homebrew/long-playthrough.json \
  --checkpoint-dir /srv/operator-private/playthrough-117 \
  --frames-per-step 1 --checkpoint-every 4096 \
  --evidence-every 64 --max-run-seconds 3600
\`\`\`

If \`status\` is \`time_budget_exhausted\` or \`cancelled\` and the operator wants to continue the **same exact plan** and game:

\`\`\`bash
python3 scripts/run_game_playthrough.py \
  --registry /srv/skeleton-emulators/cores.json \
  --target nes --core fceumm \
  --source /srv/homebrew/my-game.nes \
  --plan /srv/homebrew/long-playthrough.json \
  --checkpoint-dir /srv/operator-private/playthrough-117 \
  --resume
\`\`\`

Run an offline structural audit:

\`\`\`bash
python3 scripts/audit_game_playthrough.py \
  --checkpoint-dir /srv/operator-private/playthrough-117
\`\`\`

A continuation needs compatible savestates and a pinned exact environment and plan. Native savestates are limited by the operational JSON state/frame capacity; unsupported or oversized native serialize states **fail closed** instead of inventing a resumable checkpoint. Per-step receipt hashes cover the entire run; detailed frame/audio/controller records are sampled, not complete video capture. No unapproved ROM acquisition or decompilation is performed.

## What still needs to be built or verified

- A real gameplay-solving agent operating on screens, control mappings, goals, strategy and user-approved game-specific ending checks; the present compressed tape executes the provided inputs, not an automatic winning strategy.
- Authored branch/path coverage with alternate endings, replays from branching states, checkpoints at story transitions, credits recognition and independent victory validation.
- Multi-game long-playthrough scheduling and cross-game symbolic comparisons with rights-bound source receipts and throughput/resource quotas.
- Installed lawful core and ROM fixtures, real hardware parity and a clean end-to-end run to a **verified actual game's ending**. These were not performed by the code-writing pass.
- Durable verified learning and promoted production model weights are separate from emulator study receipts. Training limits have been enlarged, but no model-weight improvement is asserted.

The 100M figure is a **validated program step budget**, not an assertion that 100M steps have run, and not an allowance to bypass CPU, memory, process-isolation, sandbox, rights, or snapshot limits.
