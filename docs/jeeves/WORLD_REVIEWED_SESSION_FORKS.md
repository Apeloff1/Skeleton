# Reviewed alternate-playthrough forks

`world-fork` is an operator-authorized workflow for exploring an alternate
decision from an existing original-world save without overwriting that save.
The typed Jeeves tool `world.fork_preview` is read-only; it does not approve
or publish a proposal. A user must review the complete proposal JSON before
running the explicit `publish` CLI action with the parent's exact digest.

## Workflow

1. Create a canonical world with `world-canon`, then a native save with
   `world-session new`. Make choices using the session digest lease.
2. Run `world-fork --store STORE preview --world-id ID --parent-slot SLOT
   --target-slot ALTERNATE --prompt "What if..." --at-revision 0
   --choice-id CHOICE` and save the `result` object as reviewed JSON.
3. Run `world-fork --store STORE publish --world-id ID
   --proposal-file APPROVED.json --expected-parent-digest DIGEST`.
4. Use `world-fork inspect` and `world-fork compare` to verify replay
   provenance and the exact scene, ending and flag differences.
5. Run `world-fork compile --world-id ID --target-slot ALTERNATE
   --expected-world-digest DIGEST --store STORE` to emit the existing
   CSP-constrained, source-leased offline HTML5 playable. Continue the fork
   with `world-session choose`; no special runtime is required.

All files remain under the canonical descriptor-anchored world custody root.
The parent and child are independently replay-verified; the fork sidecar binds
the exact parent history, fork point, reviewed prompt and digest, original child
session and world digest. Forks are native sessions and are consumed by the
same story/world builders as ordinary saves. Replays never authorize AI
content writes. Symlinks, stale parent leases, invalid choices, forged flags,
changed world revisions and existing target slots fail closed.

New files are published by descriptor-anchored, no-clobber hard links from
fsynced temporary files, so a racing target name cannot be overwritten.
A crash between the native session write and provenance sidecar can leave a
valid but unproven native save. `world-fork inspect` refuses to claim fork
provenance until the receipt is present and verifies; no automatic overwrite
or privilege escalation is performed. SHA-256 receipts establish deterministic
integrity, not external signatures or trusted authorship. HTML5 source
verification is not device, engine, security or release certification.

## Offline visual editing

Run `world-fork --store STORE editor --world-id ID --parent-slot SLOT
--expected-parent-digest DIGEST` to produce a CSP-hashed, network-disabled
HTML editor. The editor offers only choices available at each replayed
revision and exports an **unapproved request**, never a forged session.
Use `world-fork --store STORE preview-file --request-file REQUEST.json`
to revalidate the exported request against the latest canonical source and
save the returned typed proposal for explicit review. Only the separate
`publish` action can create a native session. The browser has no custody
write access, and all edits are revalidated by Python before publication.

The visual editor bounds its replay revision inventory to 128 saved
choices. Longer native saves remain valid and playable, but the offline
editor fails closed instead of constructing an unbounded browser payload.
