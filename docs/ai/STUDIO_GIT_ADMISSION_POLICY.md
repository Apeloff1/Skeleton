# Git-aware original-studio expansion

Status: **pre-push integrity gate**, not a release or merge certificate.

The studio source ecosystem can grow toward millions of meaningful files without arbitrary 250-file, 8,000-line, 4-GiB repository, 48-draft, or 4,500-branch hard ceilings.

Before each push inspect the exact base/head Git objects and supply fresh measured repository size, projected draft count, remote branch count, and recent push count to `scripts/studio_git_admission.py`. Unknown provider capacity never means zero. Preserve source and review evidence, never pad, truncate, or invent files.

Hard guards protect complete API review (3,000 file-list entries), 100 MB Git blobs, a conservative 2 GB changed-blob/push envelope, path and tree safety, original-source-only Git submissions, and a conservative push cadence below six pushes/minute.

GitHub's ordinary PR view may truncate above 300 changed files, 20,000 lines or roughly 1 MB of diff. These are **independent review advisories** rather than arbitrary push rejections. If any is triggered, require complete per-file inventory, original-content/rights review and exact-head quality gates before integration or release. A push succeeds only at the inspected head.

Repository size beyond 5 GiB, a draft backlog above 48 and more than 5,000 branches are operational planning advisories, not pretend hard Git limits. Keep full source fidelity and adapt cadence, storage and independent review to provider and machine resources.

This gate does not certify gameplay, rights, device readiness, malware/security approval or release. Those existing fail-closed checks remain mandatory.
