# Offline encrypted spill — Studio C

This feature supplies an operator-keyed, authenticated, bounded, durable
byte spill for offline local AI. It does not download models, modify swap,
claim GPU tensor serialization, or grant provider/model execution authority.

## Install and use

The installed entry point is skeleton-offline-spill. Create a dedicated
private directory (0700 on POSIX) and a separate 32-byte random key file
(0600 on POSIX). The key is supplied again on restart and never written to
the store. Do not reuse the directory across untrusted users.

    mkdir -m 700 ~/.skeleton-spill
    python -c 'import os; p=os.path.expanduser("~/.skeleton-spill-key"); f=os.open(p, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600); os.write(f, os.urandom(32)); os.close(f)'

Supply actual lowercase 64-hex SHA-256 model and tokenizer identities.

    skeleton-offline-spill --store ~/.skeleton-spill --key-file ~/.skeleton-spill-key put --input ./buffer.bin --model-sha256 MODEL_DIGEST --tokenizer-sha256 TOKENIZER_DIGEST --context-id local-job --chunk-index 0

The commands list, verify, get, delete and prune are available. Get writes
only a new output file; existing outputs are never overwritten. Delete
requires successful decryption with the exact model/tokenizer/context identity.

## Integrity and recovery

AES-256-GCM encrypts bytes using a random nonce and authenticates canonical
manifest metadata. A separate domain-separated HMAC-SHA256 authenticates
manifest metadata for listing without decrypting all ciphertext; wrong keys
and altered manifests fail closed. The manifest schema is v2; earlier draft
v1 records are not silently migrated or accepted. Data is fsynced before
its manifest commit marker. Restart
with the same key recovers committed records; prune deletes uncommitted
ciphertext/temp objects after interrupted publication. Corrupt committed
records are not silently removed. A platform OS lock serializes mutations.
Symlinks, malformed manifests, wrong identities, corrupted ciphertext and
unknown directory entries are rejected.

Default bounds are 32 MiB per entry, 2 GiB total ciphertext, 10,000 entries
and 256 MiB disk reserve. The reserve cannot fall below 64 MiB. Disk
measurements are from the actual selected filesystem. Windows relies on OS
ACLs for key/directory protection; POSIX ownership and modes are enforced.
This feature does not claim secure erasure, key rotation, network-filesystem
locking, or accelerator memory persistence.

Focused canonical tests:

    python -m pytest -q --noconftest skeleton/testing/test_offline_encrypted_spill.py

## POSIX directory race hardening

Store operations open every ancestor with `O_DIRECTORY | O_NOFOLLOW`,
pin the root device/inode across the lock, and perform reads, writes,
renames, scans, deletion, quota accounting and fsync relative to that
descriptor. A replaced root or symlinked ancestor fails closed. CLI
input and output files use descriptor-relative parent traversal on POSIX.
This is filesystem race hardening, not secure deletion or a claim of
protection from a malicious process running with the same account's
ability to replace the lock file. Windows continues to rely on OS ACLs
and is not certified against same-user ancestor substitution.
