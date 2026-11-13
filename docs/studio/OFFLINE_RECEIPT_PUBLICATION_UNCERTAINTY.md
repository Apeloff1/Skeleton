# Offline receipt publication uncertainty — operator quarantine

The POSIX receipt publisher atomically hardlinks a fully written private file
to its final name, then checks directory durability and path identity. An
I/O error **after** that hardlink cannot safely be treated as a rollback:
another process may already have observed the final name. The publisher now
leaves the published name in place, rejects overwriting it on retry, and
removes only the independently inode-checked private temporary name.

For an uncertain result, retain the final file without copying it into a game
installation or deleting it by pathname. Obtain the expected SHA-256 from
**independent pre-publication evidence**, not from the uncertain file itself.
Then run:

```sh
python -m skeleton app inspect-uncertain-offline-receipt \
  --receipt /owner/private/receipt.json \
  --expected-receipt-sha256 <independently-pinned-64-hex> \
  --protected-root /owner/original-game \
  --protected-root /owner/private-save.json \
  --trusted-local-operator
```

Provide every source, archive, private save, signer key, detached signature,
and historical policy path as a protected root. The inspector refuses
symlinks, unpinned or noncanonical JSON, non-owner-private receipt inodes,
unknown receipt schemas and changed identities. It reads no original game
source and does not modify the receipt.

**Important:** successful quarantine inspection proves only that the
independently pinned receipt bytes are intact. It does not prove durable
publication, live game replay, save continuity, signer freshness, rights,
device qualification, or release readiness. Re-run the matching canonical
`mixed-library-handoff`, `mixed-library-continuity-handoff`, or
`mixed-library-epoch-handoff` independent inspector against all actual
game sources and private saves before relying on a handoff. Preserve all
security and release holds.
