# Unified original world director

Studio A's **world-director** connects two independent reviewed authoring
planes: chapter/act structure and original cinematic storyboards. It compiles
one playable HTML5 world with chapter headings, visited-act navigation,
author-approved caption beats and canonical choice/ending consequences.

The director is not a duplicate authoring system. Authors use
\`world-chapters\` and \`world-cinematics\` for typed proposal, offline
editing, persisted review and approval. The director consumes only their
**approved exact-world sources**, under one world-wide lease. It cannot
invent scenes, captions, cinematics, player progress or approvals.

\`\`\`sh
python -m skeleton world-director --store PRIVATE inspect --id worldone
python -m skeleton world-director --store PRIVATE compile --id worldone --expected-digests-json '{"world":"...","chapters":"...","cinematics":"..."}'
python -m skeleton world-director --store PRIVATE verify --id worldone
python -m skeleton world-director --store PRIVATE player --id worldone --slot reader
\`\`\`

The director checks both independent proof digests, all source digests,
chapter coverage, cinematic scene witnesses and exact replay of actual
player choices. It publishes HTML5, typed manifest and SHA-256 receipt.
All browser content is inert escaped JSON and DOM textContent under
strict CSP with no network or active media. Players explicitly advance
cinematic beats; no forced timers or spoiler-revealing progress.

Read-only Jeeves tools \`world.director_preview\` and
\`world.director_player\` expose inspection and session replay without
mutating sources. The builder-facing typed manifest is source-proven,
not a device-validated or release-certified game.
