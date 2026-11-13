# Replay-verified convoy league guidance

The `league-hint` command enumerates bounded player actions (movement,
gathering, crafting, merchant trading, escort, guard, strike, wait) and
attempts each against the canonical league transition under the current
save digest. Only actions that succeed in real replay are returned. Each
entry includes the resulting save digest, score, stage and terminal flags.
This is not a promise that every legal action leads to victory.

The report includes the original portable save and is itself sealed.
`league-verify-hint` rebuilds the legal action set and rejects tampering,
stale source state and fabricated movement or weapon charges. Terminal
saves expose no playable actions. The engine uses fixed candidate budgets
and never evaluates external scripts, network assets or generated code.
