# Studio A temporal continuity → verified playable handoff

The \`world-timeline\` command binds a reviewed authored event chronology to the
exact canonical world digest. It uses logical ticks, not wall-clock estimates.
It rejects causal time reversal, actor double-booking, unknown predecessors,
missing ending resolutions, unannotated scenes, unreachable flag preconditions,
and backwards scene clocks. All source edits are typed, bounded and
optimistically source-leased.

\`\`\`sh
python -m skeleton world-timeline --store ./private-worlds propose \
  --world-id harbor --actor sora --opening-note 'The beacon goes dark.' \
  --resolution-note 'The light returns.'
python -m skeleton world-timeline --store ./private-worlds inspect \
  --world-id harbor
\`\`\`

A reviewed edit file is a JSON object with \`action\` and \`value\`.
Actions: \`add\`, \`replace\`, \`remove\`, or atomic \`batch\` of up to 64.
A batch validates only the final complete chronology and never publishes an
intermediate paradox. The author must use the current timeline digest:

\`\`\`sh
python -m skeleton world-timeline --store ./private-worlds edit \
  --world-id harbor --expected-digest <CURRENT_DIGEST> \
  --operation-file ./reviewed-events.json
python -m skeleton world-timeline --store ./private-worlds compile \
  --world-id harbor --expected-digest <NEW_DIGEST>
\`\`\`

Compilation includes the canonical playable-world proof and a stable
chronological event manifest for downstream engine adapters. It does not
simulate NPC behavior, invent physical clocks, or certify real-time performance.
A world revision invalidates the timeline source lease. A receipt SHA-256
detects changes only relative to a trusted expected digest; it is not a
publisher signature.

Focused tests:
\`\`\`sh
python -m pytest -q skeleton/testing/test_jeeves_world_timeline.py
\`\`\`
