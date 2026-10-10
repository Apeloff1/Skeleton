# Game Builder: Adversarial Originality and Native-Release Review

Date: October 10, 2026. Status: active defense-in-depth, NOT legal certification.
Scope: independently authored homebrew games, archival platform inspiration,
native SDL2/C projects, binary intake, licensing notices and reviewer trust.

## Fixed material risks and executable regression evidence

| Attack | Previous exposure | Hardened control | Test |
| --- | --- | --- | --- |
| Hidden commercial ROM or DLL beside reviewed C source | Ten named files inspected, other files ignored | Exact project and rights-directory inventory; all extra content rejected | release_adversarial_matrix |
| Altered binary with old signatures | Metadata could be self-declared | Actual binary digest plus source, build/replay, credits and jurisdiction matching | native_release_intake |
| High RAM use when examining large binary | Up to 256 MB loaded into memory | Chunked SHA-256, 256 KiB read budget, 64-byte header and max file size | adversarial binary streaming tests |
| Changed file during read | Single initial inode-size check | Pre/post inode, size, ctime, mtime check, rooted descriptor traversal | race mutation tests |
| Linked or nonregular evidence | Symlinks only | Hardlinks, FIFO, directories and every symlinked ancestor refused | hardlink/FIFO/symlink tests |
| Rogue extra file in attribution folder | Credit files checked but extra material overlooked | Exact third-party-notice file allowlist | hidden-rights-payload tests |
| Duplicate JSON legal release claims | Last-wins JSON implementation differences | Nested duplicate-field denial; NaN/Infinity/overflow denial | adversarial JSON matrix |
| Caller-provided reviewer keys claimed independent | Three fake identities can manufacture an apparent panel | Separate signed Ed25519 root registry with independent root key pin | release_trust_anchor |
| Same Ed25519 key signs as multiple reviewers | Reviewer IDs differentiated keys only nominally | Reject duplicate public keys, alias IDs and root/reviewer key reuse | trust-key-collision tests |
| Historic reviewer policy replay | Valid signatures reused under revoked old trust | Signed policy epoch, external minimum epoch, time bounds and revoked reviewer check | rollback and registry-timing tests |
| Signatures issued before reviewer enrollment | Old approvals could inherit new trust | Review signing time must not predate signed trust issuance | antedated-signature test |
| Unreviewed new region or store channel | Signed receipt presented in another territory | Exact reviewed jurisdictions/platform/channel match signed candidate and root | territorial scope tests |
| Legacy unpinned review reported independent | Caller could self-supply all signing identities | Legacy reports only structurally complete signatures, NOT verified independence | legacy/native pinned gate tests |
| Long repeated text denial of service | Quadratic match extension and 32-position truncation | Exact token suffix automaton in O(n+m) per comparison | 900 seeded oracle comparisons and repeated-word cases |
| Short protected dialogue verbatim overlooked | Threshold focused on long runs | Six/seven-token narrative reuse marked for human review, not legal judgment | narrative reuse test |
| Invisible or reversed attribution notice | ASCII controls filtered; Unicode bidi controls survived | Reject Unicode format/control/surrogate/paragraph separators | Unicode author/license spoofing tests |
| Forged proof of native execution | MZ or ELF magic sometimes mistaken for executable validation | Explicit executable-structure, boot, compiler, legal and release flags stay false | native intake receipt tests |
| Cross-project source and licence substitution | Detached approvals could refer to another artifact | Hashes bind world, C source, binary, credits, proof, channel and destination | multi-domain signature mutation tests |

## Remaining adversarial threat classes (NOT marked complete)

### P0: Law and independent authorship
- Semantic adaptation may copy substantial protected plot, characters, maps,
  audiovisual arrangements or lyrics without any exact byte/text match.
- AI training contamination, memorization and hidden reference corpora require
  independent lawful data provenance. Negative scanner results are not proof.
- Cropping, frame interpolation, color swaps, resampling, reorchestration,
  translating a narrative and derivative character designs evade naïve hashes.
- Moral rights, attribution, copyright, trademarks, design patents and trade
  secrets are distinct; credits alone cannot grant licensed copying.
- Historical abandonware, freeware, fan-game labeling, homebrew or a new
  device destination do not erase the original game's protected expression.
- Reviewer independence and legal qualifications are verified operationally
  by a trusted administrator, not by a mathematical plagiarism percentage.

### P0: Native targets and real execution
- Synthetic PE-like binary headers are not proof of compiled/runnable programs.
- Every game family requires its own cartridge/header/mapper/firmware checks.
- All console and PC-era exports must be compiled using qualified lawful
  toolchains, tested in emulators when lawful, then on real hardware where needed.
- Region-specific storefront terms, boot mechanisms, anti-circumvention laws,
  input/audio timing, save-memory support and crash recovery remain separate.
- Real binaries must be connected to reproducible source, actual compiler logs,
  gameplay tests, and external signed build provenance.
- Third-party console signing keys and licensed proprietary SDKs must not be
  stored inside the project or generalized to other platforms.

### P1: Filesystems, infrastructure and policy trust
- Hostile kernel/filesystem attackers can evade user-space file checks; immutable
  snapshots and distribution-time revalidation remain necessary.
- Windows ACLs, reparse points, case-insensitive path collisions, NTFS streams,
  network share TOCTOU, macOS bundles and code-signing demand dedicated gates.
- The root-key pin and monotonic minimum policy epoch must be provisioned
  OUTSIDE the reviewed game repository by an independent administrator.
- Reviewer account compromise, key rotation, transparency logs, trusted time,
  and revocation distribution require organizational security controls.
- The root signature proves who authenticated a reviewer registry; it does not
  establish actual copyright title or publisher permission.
- Source packages can be edited between verification and distribution unless
  final artifacts are made immutable and rechecked.

### P2: Performance and false-positive handling
- Dense 4096-pair similarity cohorts can still cost CPU even with linear
  per-comparison matching; shard across consumer-grade bounded memory.
- Tiny conventional programming phrases often match innocently. Do not
  automatically treat matches as legal copying.
- Global historical hardware census is not complete. Catalogued entries are
  source-referenced candidates rather than universally verified targets.
- Specialty audio formats, animation frames, 3D model topology and level
  semantics need independent lawful reference sets and specialist analysis.
- Reviewer decisions need traceable disagreement, appeal, takedown and
  counterclaim procedures before broad publication at scale.

## Live validation contracts

Focused workflow: .github/workflows/game-hardware-archive.yml
Important modules: plagiarism_guard.py, media_similarity.py, asset_credits.py,
release_trust_anchor.py, release_assurance.py, native_release_intake.py,
release_pipeline.py, legal_paths.py and legal_native_export.py.

Focused regression suites:
- test_game_builder_originality_adversarial.py
- test_game_builder_release_adversarial_matrix.py
- test_game_builder_release_trust_anchor.py
- test_game_builder_native_release_intake.py
- test_game_builder_release_assurance.py
- test_game_builder_asset_credits.py
- test_game_builder_plagiarism_guard.py
- test_game_builder_legal_paths.py

The independent review gate must use run_pinned_native_release_gate for cases
where external reviewer identity matters. The legacy unpinned gate may confirm
structure of reviewer signatures, but never independent authority.

Never conflate:
1. Candidate content and legal evidence;
2. Actual game/source byte hashes;
3. Independent reviewer signatures;
4. Genuine native execution;
5. Rights-holder and publisher authorization;
6. Worldwide proof of non-plagiarism.

No automated system in this repository currently guarantees (4), (5), or (6).
No digital artifact alone licenses third-party commercial game IP.

Minimum requirements before publication:
author provenance, lawful target SDK/hardware access, reviewed third-party
licenses/credits, signed authority snapshot from an external root, complete
byte-bound review, actual qualified native gameplay validation and a separate
responsible-publisher decision. Change any component, and revalidate.
