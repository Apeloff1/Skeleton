# Studio A — browser-playable authored consequences

The reviewed faction and evidence verticals now emit interactive offline
HTML that renders canonical scenes, legal choices, source-earned flags,
reviewed faction reputation and discovered clues. The browser player uses
`textContent` exclusively for authored text and a SHA-256 CSP script
allowlist; embedded JSON escapes angle brackets to prevent script breakout.

A player can traverse legal choices and observe the same faction saturation
and clue dependency closure as the authoritative Python replay. Locked clues
are never inserted into the visible DOM. The HTML is source-derived and
verified byte-for-byte with the companion handoff/receipt by `world-factions
verify` or `world-evidence verify`. The independent player-session CLI
remains the durable, authoritative save/replay surface; browser state alone
is not an authenticated save or an assertion of earned gameplay progress.

The shared renderer supports both extensions simultaneously for future
combined playable assemblies. Neither browser execution nor device
qualification is claimed without actual tests and consumer evidence.
