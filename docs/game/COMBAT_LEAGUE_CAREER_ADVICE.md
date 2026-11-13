# Replay-Verified Coaching Advisor

Use \`python -m skeleton combat-career-advice demo\` for a real
one-season comparison of coaching choices. The advisor replays a rest
choice and up to four legal stat-training choices for one authored
entrant. It scores the actual season winner, earned tournament points
and preservation of scarce training tokens. It never grants a reward
or advances the supplied saved session.

\`advise --session-json --target-id\` returns each evaluated action,
its league replay receipt and the recommended action's canonical
predicted save. \`verify --session-json --advice-json\` reruns every
candidate and rejects forged scores, source digests and predictions.

The claim is explicitly \`one_season_replay_only\`. This is not a
proof of globally optimal multi-season play. Unknown entrants, capped
stats, terminal sessions and malformed saves fail closed.
