# Reviewed original cinematic storyboards

Studio A's cinematic lane is an **original text-only storyboard system**. It
does not import film, sound, likeness, copyrighted scripts, remote URLs or
active media. Every scene entry may have a bounded sequence of authored
arrival/action/reaction/departure beats. Durations are engine metadata hints,
not forced playback timers; the offline HTML5 player requires explicit
keyboard/button activation before progressing. A scene's normal world
choices remain available only after its authored sequence is complete.

## Operator workflow

Create a canonical world with \`python -m skeleton world-canon\`. Prepare a
bounded JSON proposal containing \`prompt\` and \`sequences\` (sorted by
scene ID). Each sequence has \`scene\` and \`beats\`; each beat has \`id\`,
\`cue\`, \`caption\` and integer \`duration_ms\` (500–15000).

\`\`\`sh
python -m skeleton world-cinematics --store PRIVATE propose --id worldone --file proposal.json
python -m skeleton world-cinematics --store PRIVATE publish --id worldone --file reviewed-source.json --create
python -m skeleton world-cinematics --store PRIVATE inspect --id worldone
python -m skeleton world-cinematics --store PRIVATE editor --id worldone --expected-digest SOURCE_DIGEST
python -m skeleton world-cinematics --store PRIVATE approve --id worldone --expected-digest SOURCE_DIGEST --note "Original captions reviewed"
python -m skeleton world-cinematics --store PRIVATE compile --id worldone --expected-digest APPROVED_DIGEST
python -m skeleton world-cinematics --store PRIVATE verify --id worldone
python -m skeleton world-cinematics --store PRIVATE player --id worldone --slot player1
\`\`\`

The offline editor exports an **unapproved** source. Publish with an exact
previous digest, review again and compile the new approved digest. Typed
Jeeves tools \`world.cinematics_propose_preview\`,
\`world.cinematics_preview\` and \`world.cinematics_player\` are read-only.
They never approve, persist or claim verified gameplay.

## Contracts and safety

A world digest lease ties every storyboard to its exact original world
revision. A world-wide O_EXCL lock serializes edits, approval and compiled
artifact publication. All authored scenes must be reachable through actual
world choices and flags; proof includes concrete entry witnesses. The engine
handoff carries typed scene/caption/duration descriptors, exact digests and
the explicit user-advance timing policy. The offline player and editor use
strict CSP script hashes, inert escaped JSON, textContent for untrusted
captions and no network or external assets.

Compilation produces a standalone HTML5 playable, an engine descriptor and
a SHA-256 artifact receipt. Verification rereads all artifacts with
descriptor-anchored, no-follow custody. Tampered receipts, symlinked output,
stale edits, forged sessions and missing reviews fail closed. This is a
source-proven handoff, **not device, accessibility or release certification**.
