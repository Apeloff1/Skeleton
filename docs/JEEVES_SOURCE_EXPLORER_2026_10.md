# Jeeves source explorer & exact patchset cockpit — 2026-10-13

**DX-22:** Source explorer integrated into the *existing* authenticated
localhost Game Studio UI. Source-content search accepts literal UTF-8 query,
optional repository prefix and case sensitivity; supports snapshot-bound
path cursors and bounded pages. Each result exposes real source SHA-256.

**DX-23:** Line-based navigator uses a selected exact source identity to
read capped line ranges rather than returning entire modules. Search hits
populate filename, line and source hash; stale source reads refuse mismatches.

**DX-24:** Operator-reviewed multi-file exact-hunk change proposals are
available in an explicitly approved UI section. The server preflights all
paths and source SHA-256 fingerprints, constructs deterministic diff reviews
and does not apply commits, trigger model self-updates or widen tool authority.

The UI renders all returned source/diff content with \`textContent\`
instead of HTML injection. No tests were run during this build-only pass.
