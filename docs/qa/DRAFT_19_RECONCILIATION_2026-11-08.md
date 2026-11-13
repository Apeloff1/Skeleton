# 19-draft reconciliation custody — 2026-11-08

**Main-based qualification candidate only (2026-11-08).** Review base is now `main`, not the #5074 feature branch, to require full integrated exact-head CI. The branch retains [#5074](https://github.com/Apeloff1/Skeleton/pull/5074) at reviewed parent `2018a908b10ca298982439bfdd864fdf246a0a18` in its Git ancestry; earlier #5074 baseline `5166439f8f79319efc6099f49b05e28b19abef6c` is historical. The 19 recovered source changes remain separate in the branch tree. This retarget is **not** promotion to merge, device, security, or release readiness. The original draft heads and branch protections remain unchanged. This document is a **source-review ledger**, not a CI, merge, Windows/WSL2, native inference, or release approval. A partial GitHub file listing is not a complete semantic diff; all claims below are limited to examined paths and observed workflow results.

## Disposition by original PR

| Draft | Source custody disposition | Required independent work |
|---|---|---|
| #5069 | Windows ZIP rejects Unix special inodes on #5074 with more restrictive unsupported-compression checks; source content differs from donor | Keep focused ZIP tests and reconcile #5073 overlap |
| #5062 | Major 1,648-file AI parity / installer foundation overlaps #5074; latest donor head not independently mergeable alongside it | Exact tree/architecture and full integration CI |
| #5056 | Iterative deep scene ancestry and bounded regression already present on #5074 | Verify high-depth cycle tests on final head |
| #5055 | Loopback Compose binding already implemented in #5074; test path differs | Preserve source-only regression, verify live Compose |
| #5049 | Same loopback security objective; redundant source edit | Do not double-apply, verify opt-in network policy |
| #5038 | GGUF standalone preliminary header preflight not wired; unsafe to interpret as a model loader | This child strengthens existing `skeleton/local_ai/model_loader.py` descriptor custody instead; full metadata, rights and real inference remain separate |
| #5033 | Overlapping loopback Compose repair with alternative fixture | Do not double-merge; verify Docker configuration |
| #5028 | Overlapping loopback Compose repair with alternative fixture | Do not double-merge; maintain remote-access policy |
| #5022 | Explicit quarantine; incomplete flight HTTP write and event encoding, failures in source/native checks | Preserve review-only and selectively extract only independently proven tests |
| #4994 | Hardlink and replacement-resistant canonical Jeeves world-source reads, mirrored source and regression already present on #5074 | Continue POSIX custody and Windows portability review |
| #4991 | Historical Godot export snapshot, conflict/stale ancestry; no complete qualification | Compare per-path against current Godot export and port only justified code |
| #4990 | Gameplay state migrations integrated with additional payload/migration bounds and tests | Full save-plane compatibility, rollback and replay evidence |
| #4902 | Source-only historical sandbox branch; candidate already contains guarded executor, strengthened audit retention/sink custody | Source/audit review for any remaining unique security cases |
| #4889 | Stacked architecture, Python syntax and LocalAPI changes overlap #5074 foundation | Preserve canonical import boundaries and exact mirror pins |
| #4885 | AI mirror/source-index foundation overlaps #5074; source qualification green on #5074 at baseline SHA | No ownership cutover, full CI still necessary |
| #4870 | Older stacked 1,647-mirror and native fixture lineage overlaps #5074 | Do not merge ancestor and composite separately |
| #4853 | First-install Python image/setup/recovery lineage overlaps #5074 | Independent Windows/WSL2/Docker device/rollback proof |
| #4838 | Older Forge/audio and ownership parity overlapping #4836 and #5074 | Keep independent signoff and check retained count |
| #4836 | Earlier Forge/audio parity root; superseded by broader AI mirror reconciliation | No duplicate mirror merge or authority promotion |

## New, independently reviewable security work

- Anchor every component of the GGUF artifact path to POSIX no-follow directory descriptors rather than allowing symlinked intermediate directories.
- Deny hardlinked file artifacts and changed paths even when content digests happen to agree.
- Keep the immutable SHA-256 and rights/CAS checks, strict no-fake-inference receipt, file size budget, and existing legacy-qualification interface intact.
- Run the existing `skeleton.testing.test_local_ai_gguf_qualification` suite plus new `skeleton.testing.test_local_ai_gguf_custody` regression at this child's final head.
- **Never** report `artifact_verified_not_loaded` as model activation, full GGUF metadata safety, tensor validation, license ownership or device/launch certification.

## Admission and rollback

This branch includes #5074 in Git ancestry and is now compared directly with `main` solely for **complete integrated exact-final-head qualification**. It must not be merged to `main` without rechecking ancestry, duplicate source, final-head tests, architecture/mirror index, mandatory malware/secret/dependency/workflow/CI gates, independent review and device checks. To revert the incremental change, revert its dedicated commit only after confirming downstream integration dependencies. Keep #5022 and the historic recovery branches quarantined.
