# Offline Chroma HNSW — descriptor-bound index custody

This stacked source patch closes a time-of-check/time-of-use gap in the
previous offline Chroma file-custody reader. It is review-only and uses
no production database or running Docker container.

## Failure mechanism

Checking `root / segment_uuid / header.bin` with a stat call, then opening
the same pathname after a separate directory listing, is not enough.
The segment directory or the binary itself can be replaced between
those operations. Merely setting `O_NOFOLLOW` on a **file** does not
protect an intermediate symlink in its parent directory.

## Implemented protection

- Validate the segment directory's inode, permissions and identity,
  then open it once with `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`.
- Require the opened directory's device/inode/mode/size/timestamps
  to match the audited pathname. All subsequent file listings use
  `os.listdir(directory_fd)` on that exact object.
- Every five-file read uses `openat` semantics via
  `os.open(filename, O_NOFOLLOW, dir_fd=directory_fd)`. No index
  file can redirect the process through a swapped parent pathname.
- Require the opened file descriptor to match a nofollow
  `os.stat(filename, dir_fd=directory_fd)` identity both before and
  after streaming the bounded SHA-256 hash.
- Re-verify the segment directory pathname and opened directory
  inode, plus a fresh descriptor-relative file list, before
  accepting its accumulated binary digest.
- If descriptor-relative, nofollow directory access is unavailable,
  fail closed: no fallback to path-only reads.

## Adversarial source cases

Temporary test fixtures rename a segment directory after its
descriptor has been opened, replace the path with a symlink, and
challenge the opened file set. A second fixture swaps an index binary
to a symlink immediately before an `openat` call. Both must deny the
audit without traversing attacker-controlled paths.

Additional fixtures explicitly require integer directory descriptors
for all five HNSW binary hashes, while the earlier missing index,
unsafe file, malicious pickle, SQLite WAL and changing binary tests
remain mandatory.

This is a defense against observed path redirection during a
*read-only file* audit. It does not establish that there was
no concurrent writer before the cold archive, that Chroma's native
graph is valid, or that Mongo/SQLite/Chroma form one atomic snapshot.

```sh
python -m compileall -q \
  scripts/local_ai_restored_chroma.py \
  skeleton/testing/test_local_ai_restored_chroma.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_restored_chroma.py
```

Real physical proof still requires an operator-controlled offline
archive with exact receipts. The source test suite is not a release,
migration, protected-chat, vector-query or cross-store recovery gate.
