# Explicit reviewed game source publication — 2026-10-13

**DX-44 — reviewed source bundle.** The existing GameWorkspace proposal
store can now assemble an exact-source multi-file review with original vs
candidate unified diffs, per-file SHA-256, inspected current source bytes,
source paths and bounded output. Multiple proposals aimed at one source,
stale bases and already accepted proposals are refused before user approval.

**DX-45 — actual source commits.** After inspecting the *full* source diff,
the human explicitly approves every proposal and its exact proposed SHA-256.
\`studio.production.commit_bundle\` re-fetches current source evidence and
checks the expected review digest before calling **canonical**
\`GameWorkspace.commit\` on every approved file. This finally moves
reviewed game builder/editor/native project artifacts from proposal custody to
the active original game tree. No other source writer is created.

**DX-46 — honest partial failure.** A batch uses one-to-one CAS checked
source commits, **not an all-or-nothing filesystem transaction**.
If a later write fails, the receipt lists already committed and outstanding
proposal IDs without claiming a complete release. Any retry requires a new
review and independent human authorization. Truncated diffs must be split
into smaller independently reviewed batches before publication.

A production game still requires runtime/device acceptance, packaging,
release licensing and operator signoff; committing its reviewed sources
alone does not qualify a native binary or product release.

**Build-only status:** no test suites run in this workpass.
