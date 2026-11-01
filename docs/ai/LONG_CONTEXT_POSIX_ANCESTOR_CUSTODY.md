# POSIX token-spool ancestor and selected-source custody

LongContextSpool now traverses every POSIX ancestor from the filesystem
anchor using held directory descriptors and O_DIRECTORY|O_NOFOLLOW.
Creation of the root, objects and checkpoints is descriptor-relative.
A symlink substituted at any ancestor cannot redirect a later write to
an attacker-controlled directory. The final pinned root remains valid
when a path is renamed, and no existing checkpoint is overwritten.

The installed long-context CLI uses the same no-follow ancestor walk for
selected token-sequence input. It checks a regular-file descriptor,
rejects oversized sources before reading, and compares descriptor identity,
size, mode and modification metadata before and after bounded materialization.
On POSIX it also rechecks the final selected filename relative to the pinned
parent descriptor, rejecting name substitution even when replacement content
is byte-for-byte identical. These checks are detection fences, not protection
against a malicious same-UID writer able to modify files and metadata.
On Windows, path-based fallback remains explicitly unqualified against
same-user ancestor races;
this is not a claim of a native handle-relative Windows security boundary.
The spool still requires trusted checkpoint digest custody for rollback
detection and does not serialize model KV tensors.

## Bounded full-chain restart audit

Use `python -m skeleton.ai.model_runtime.long_context_cli --root ROOT
--tokenizer-digest DIGEST audit --checkpoint CHECKPOINT
--max-checkpoints 4096` to walk the entire immutable progress chain to its
zero-cursor genesis. The verifier rechecks every checkpoint digest, source,
tokenizer, object identity, and strictly descending cursor. A missing ancestor,
wrong tokenizer, rollback, or exhausted audit bound fails closed. Receipts
expose only digests, cursor and verified checkpoint count, never token IDs.
This audit does not authenticate the publisher or replace a trusted external
latest-checkpoint replay fence. It does not qualify KV tensor persistence.
