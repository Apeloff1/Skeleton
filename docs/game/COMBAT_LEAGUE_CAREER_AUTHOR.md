# Coaching Career Source Editor

Run \`python -m skeleton combat-career-author demo\` for a canonical
editable Harbor League career. \`new --source-json\` imports original
authored source. \`edit --author-json --edit-json\` supports
\`rename_career\`, \`set_seasons\`, \`set_training_tokens\`,
\`set_league_rounds\`, and \`set_entrant_stat\`.

Every edit requires \`expected_source_digest\`. The editor checks the
lease, revalidates the complete career and underlying tournament source,
then appends a replayable edit event. Invalid roster stats, exhausted
budgets, stale revisions and conflicting source fail closed.

\`preview --author-json --choices-json\` runs actual seasons through
the league simulator and returns canonical save and standings.
\`verify\`, \`export\`, and \`import\` check every edit and bundle.
Hashes detect accidental or deliberate alteration but do not prove
authorship. No external assets or proprietary content are imported.
