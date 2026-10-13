# Jeeves multi-file exact-source refactoring — October 2026

**DX-18.** A reviewed \`source.patchset.preview\` adapter now accepts
1–8 source files and 1–24 unique non-overlapping exact replacement hunks per
file, with an aggregate 72-hunk / 380 KB input / 512 KB diff budget. All
source identities are optimistic SHA-256 checks on the unchanged original
files, not on intermediate candidate output. A single stale, ambiguous,
overlapping, private or unscanned source aborts the *whole* proposal.

**DX-19.** Each file is fed through the **existing** canonical
\`AppwideInventory.propose_source_revision\` review boundary. The result is a
source-pinned proposed diff with exact changed span receipts, line references,
old/new hashes and content digests. No new writable source owner, execution
service or autonomous code modification permission is created.

\`\`\`python
receipt = runtime.invoke("source.patchset.preview", {
    "expected_snapshot": scanned_digest,
    "reason": "Coordinate source-owned refactor across dependent Studio modules.",
    "patches": [{
        "path": "skeleton/ai/game_builder/example.py",
        "expected_sha256": original_full_source_sha256,
        "edits": [{"old": "def old_name(", "new": "def renamed_name("}],
    }],
}, authorized=True)
\`\`\`

This builds a deterministic **review artifact**, not an applied commit or
an automatically validated patch. Every affected source must be freshly
read and explicitly approved again at actual write time. No tests executed
in this milestone workpass.
