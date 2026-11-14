# Human-controlled combat campaign acceptance

`python -m skeleton combat-campaign-accept demo` exercises an original
playable multi-encounter campaign, with actual hero choices, deterministic
opponent responses, health carryover, earned rewards and terminal victory.
The source-bound decision board must predict each canonical next state.

`combat-campaign-accept accept --source-json JSON --actions-json JSON`
returns a replayable acceptance receipt. `verify --source-json JSON
--receipt-json JSON` reruns the full source-to-play-to-replay-to-export path.
Acceptance checks midpoint restart, interactive JSON-line checkpoints and
portable save/import. It rejects forged snapshots, stale sources, impossible
rewards, losing prefixes and transcript overflow.

Input is bounded to 32 player actions, 64 KiB of authored source and 2 MiB
of interactive transcript. A digest proves internal consistency, not
publisher identity, rights ownership or release qualification.
