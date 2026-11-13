# Private NPC conversation transcript custody and restart

This source-bound vertical persists **intermediate** dialogue responses before
they become a canonical world choice. The transcript is a private file under
the same descriptor-anchored world-wide lease used by world, cast and saved
session custody. It binds to the exact world/cast/dialogue/session digests,
stores a bounded 128-response trace and a deterministic SHA-256 hash chain,
and independently replays every response on read.

\`world-dialogue-transcript begin\` requires world ID, player slot,
conversation ID and expected session/dialogue digests. \`append\` requires
the exact transcript digest and a response ID. \`inspect\` resumes from
the canonical next node, not from client-supplied mutable state. \`commit\`
requires a completed response trace and atomically admits its canonical
world choice under the exclusive world lease. A crash between session
publication and receipt publication leaves a stale transcript that refuses
duplicate commits; it does not silently replay the choice twice. \`cancel\`
discards an uncommitted transcript without changing the player session.
\`verify\` validates the last receipt against the current source and session.

Read-only Jeeves \`world.dialogue_transcript_preview\` exposes verified
progress without granting publication or review authority. Transcripts do
not contain API credentials, provider state or model chain-of-thought.
The session write and receipt are individually fsynced but are not a single
filesystem transaction; interrupted publication requires explicit recovery
rather than an automatic success claim. This is not device/release certified.
