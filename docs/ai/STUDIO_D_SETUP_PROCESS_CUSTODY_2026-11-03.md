# Studio D — guarded first-install secret custody

The canonical setup entry point now serializes `.env` bootstrap across
independent Windows launcher, CLI, and installer processes. The persistent
`.skeleton-setup.lock` is not a secret, is never unlinked on release, and
is identity-checked before and after lock acquisition. On POSIX, advisory
flock is used; on Windows, msvcrt byte-range locking is used. A bounded wait
fails closed rather than silently generating conflicting service credentials.

Existing `.env` input must be a stable regular file, cannot be a symbolic
link, and is bounded to 256 KiB. Secret output uses a private temporary file,
fsync, atomic replace, and POSIX parent-directory fsync. Setup remains
idempotent and does not fetch model weights, establish inference readiness,
or authorize any backend action.

## Focused acceptance

`python -m pytest -q skeleton/testing/test_setup_process_custody.py`

Run the canonical installer and application assembly suites on the exact
commit, then full required security and CI gates. Execute the Windows 11
WSL2/Docker clean-host install with separate signed readiness receipts.
This source change is **not** consumer/device qualification. A hostile
operator-owned parent directory is outside this lock's threat model.
