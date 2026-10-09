# Offline Standalone AI — Adversarial Engineering Review

**Review date:** 2026-10-09  
**Scope:** PR #3593, application-shell offline native/GGUF inference, Windows
console distribution, local FTS5 document index, revisioned conversations,
SQLite indexing queue, portable snapshots and Windows per-program egress rules.  
**Status:** Code changes committed; final-head CI and real-device acceptance
**not yet passed or signed**. No verified claim of whole-product air-gapped
operation. This ledger is review evidence, not a production security
attestation.

## Adversary and ownership boundaries

An attacker may supply untrusted local documents, a corrupt or altered SQLite
database, a forged snapshot folder, a symlink or swapped directory, a stale
worker lease, a competing destination file or an altered model manifest. The
AI-generated text itself must be treated as untrusted context, never a tool
permission or a canonical system instruction. No hosted provider or crawler
authority is introduced by the application-shell library/queue.

Out of scope for security guarantees: privileged OS compromise, hostile
libraries in a user-supplied GGUF executable, malicious wheel post-install
code, independent cryptographic provenance, compromised local account, and
all traffic from unrelated executables. Per-program firewall rules are
opt-in, not proof of an isolated host.

## Findings and implemented repairs

| Finding | Adversarial scenario | Repair | Regression |
| --- | --- | --- | --- |
| F01: Import-time failure | Malformed Python indentation in snapshot manifest and audit import prevents standalone recovery commands | Corrected Python indentation; P2 workflow now compiles offline modules before dependency setup | Workflow parse step; exact-head CI pending |
| F02: Stale path replay | Restoring a queue on a new device silently executes original directory/library paths | Restore changes all queued/running/failed jobs to non-retryable cancelled state; only explicit new enqueue can run | `test_offline_snapshot.py` |
| F03: Lease-to-data gap | Expired worker can commit stale FTS changes and only fail *after* publishing when recording receipt | Library accepts last-moment lease callback inside its transaction; queue verifies active token and expiry before commit | `test_offline_index_queue.py` stolen/expired lease cases |
| F04: Symlink swap | Attacker replaces enumerated nested directory with a link to private files before open | POSIX dirfd traversal with `O_DIRECTORY|O_NOFOLLOW` for each component; Windows detects path redirection where possible | `test_offline_library.py` parent swap and binary-NUL tests |
| F05: Snapshot overwrite race | Another process creates snapshot directory after absent-path check | Exclusive `mkdir` + hardlinks; manifest published last; incomplete folder never verifies as complete | `test_offline_snapshot.py` competing directory + incomplete manifest |
| F06: Restore rollback race | A different process substitutes a file after first destination is published; later restore failure deletes substitute | Cleanup only unlinks a path if it still refers to the inode created by this restore | `test_offline_snapshot.py` competing replacement |
| F07: Forged queue completion | SQLite file is structurally valid but `result_json` has negative metrics or is present for a queued job | Ordinary queue read/claim now checks state, attempt, timing, metrics and JSON nonfinite constants | `test_offline_index_queue.py` forged results |
| F08: Cross-root unbounded index | Importing many individually bounded folders grows SQLite without aggregate limits | Transactional aggregate cap: 10,000 documents / 128 MiB of stored UTF-8 text | `test_offline_library.py` per-root aggregate rollback |
| F09: Queue storage exhaustion | An operator or caller submits thousands of unique jobs | Atomic durable queue cap at 5,000 records while retaining active-job deduplication | `test_offline_index_queue.py` |
| F10: Semantic-audit allocation | Large valid SQLite strings trigger excessive `fetchall()` memory allocation | Stream rows and reject when text/blob budget is exceeded before accumulating all records | `test_offline_audit.py` |
| F11: Index projection drift | Unchanged source digest hides damaged FTS records | Explicit reindex verifies both stored body and FTS row, repairs divergence and prunes orphans | `test_offline_audit.py` |
| F12: Insufficient snapshot admission | SQLite `integrity_check` passes when transcript checksum, FTS references or job receipts are inconsistent | Additional read-only semantic audit required before admitting a snapshot source and restored copy | `test_offline_audit.py` forged/corrupt state |
| F13: Weak local privacy defaults | New local conversation/document databases are created with broad filesystem permissions | POSIX new-files set to 0600; existing ACLs remain operator-controlled | `test_offline_audit.py` |

| F14: SQLite companion redirection | Selected database has a symlinked `-wal`, `-shm` or `-journal` companion that points outside the intended directory | Shared SQLite path admission rejects symlink/special-file companions before opening offline workspace, library, queue, snapshots and audits | `test_offline_sqlite_safety.py` |
| F15: Incomplete release qualification | Syntax defects or a frozen EXE missing local queue/recovery code escape review | Exact-head P2 pipeline now parse-checks offline Python before dependency installation; Windows installer smoke exercises queue completion, restored job quarantine, and semantic re-audit | P2 Local Inference + Windows Installer; exact-head verdict pending |

## Invariants checked by acceptance tests

1. Document indexing never fetches a URL or executes indexed source text.
2. The source directory is explicitly selected, file inputs are bounded UTF-8
   text and ingestion rejects symlinks, binary files and over-budget bodies.
3. Every accepted indexing batch commits atomically. Failed lease checks,
   source validation and aggregate quota checks preserve prior index state.
4. Complete AI chat turns persist only after validated generation and a
   successful CAS write; a competing conversation revision fails closed.
5. Recovered indexing queue records never revive actionable paths/leases
   from their source device. Original queue data remains unchanged.
6. Snapshot source and copied bytes pass SHA-256 and domain-specific semantic
   checks before publication; a source manifest is **not** cryptographically
   authenticated.
7. Snapshot and restore destination publication never intentionally replaces
   an existing file or directory. Partial publication has no manifest and is
   rejected by verifier; rollback does not unlink substituted foreign files.
8. The frozen Windows console supports native inference smoke, no-model
   local FTS5 search, queued indexing and portable database recovery without
   requiring a separate system Python installation.
9. Readiness checks and semantic audits do not claim full model intelligence,
   OS network egress isolation, or signed safety certification.

## Remaining adversarial concerns and qualification blockers

- **Model executable trust:** SHA-256 is content identity, not publisher
  authenticity; malicious operator-supplied llama.cpp executables or installed
  Python wheels can execute code. Obtain external provenance and test in a
  sandbox with constrained OS privileges.
- **Windows directory reparse races:** Python's portable stdlib does not
  provide equivalent POSIX per-component `dir_fd` containment on Windows.
  Defensive path resolution is best-effort; a strict OS-native handle-based
  Windows implementation is a separate task.
- **Filesystem TOCTOU and SQLite companions:** Companion-path admission and
  POSIX dirfd reads reduce redirected-path attacks, but a malicious same-user
  process can still mutate paths after admission; the stdlib does not confer a
  full OS sandbox. Restrict directory write access.
- **Local account compromise:** Same-user processes can alter plaintext
  SQLite, snapshots and integrity manifests. OS ACLs/encryption and trusted
  backups are required; unsigned checksums are not authentication.
- **Cross-file backup consistency:** Each SQLite file is individually
  consistent; the group is not an atomic checkpoint across conversations,
  index and job queue. Stop writers when a synchronized restoration is needed.
- **Writer cancellation:** A rollback/fencing check rejects stale state, but
  it does not terminate an arbitrary malicious local executable or defend
  against a hostile kernel/filesystem.
- **FTS token index internals:** Semantic auditing checks row and body
  correspondence; it does not independently prove every token-position
  posting in the SQLite FTS5 shadow tables. Use explicit verified source
  reindexing for repair and OS/SQLite integrity checks for corruption.
- **Readiness / airgap:** No signed artifact release, full crawler parity,
  real-GGUF hardware qualification, whole-application Windows installer
  acceptance, or OS-wide network quarantine is claimed by this review.

## Release decision gate

Do not merge or sign this milestone as complete until all required exact-head
GitHub CI workflows have succeeded, including P2 Local Inference, Windows
Installer smoke, App Assembly, Backend Quality and Merge Readiness. Also run
genuine licensed native/GGUF model acceptance on the target hardware with
independently controlled network egress; verify local-data recovery from clean
installation after a process interruption. The frozen native smoke fixture is
**not** a trained model acceptance test.

A passing static review or successful commit does not substitute for those
runtime outcomes.
