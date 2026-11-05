# Independent rollback custody for offline KV migrations

Production `OfflineKVPageTierService.from_trusted_handles` requires an
independent durable generation/digest compare-and-swap anchor. The anchor MUST
be stored outside the SQLite journal, must not reset across restarts and must
be controlled by the authenticated application. No anchor keys, page tensors,
prompt content or model weights are written to the journal.

For a **new installation only**, call `bootstrap_new_journal_anchor()` once
after securely provisioning the empty SQLite database and independent anchor.
On restart, supply the existing anchor and do not bootstrap. Before any new
physical movement, the journal authenticates bounded historical rows and
compares their canonical digest to the independent anchor.

The RUNNING intent commits to SQLite before the anchor advances. A completed
physical migration commits its receipt before a second anchor advance.
A crash or CAS failure between these commits leaves a detectable mismatch,
quarantines the journal, and prohibits automatic retry. An old SQLite snapshot
cannot be silently accepted when the independent anchor has advanced.

This design is deliberately fail-closed rather than an atomic distributed
transaction. It cannot prove physical tier residency or recover an uncertain
partially completed adapter operation. A trusted operator must reconcile the
backend, journal and anchor. The simulated CAS in deterministic tests does
**not** provide production anti-rollback or device qualification.

## Production SQLite file preflight

The production app constructor rejects ephemeral/in-memory SQLite, attached
databases, disabled/weak synchronous modes, journal modes without durable
rollback, symlinks, hardlinks and non-private POSIX owner/mode settings.
It requires an owner-only regular file with mode 0600 and synchronous FULL
or stronger. This is a preflight, not a substitute for a securely opened
and retained OS inode handle. Non-POSIX ACL qualification is held until a
platform-specific trusted adapter is implemented; simulation remains
available for deterministic tests only.
