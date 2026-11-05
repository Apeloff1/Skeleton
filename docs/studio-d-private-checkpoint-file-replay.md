# Owner-private checkpoint-file replay

The Studio D offline original-game audit can replay a bounded chain of
independently pinned historical handoffs without placing large checkpoint JSON
in process arguments or shell history. This is a POSIX-only source-level audit,
not device execution, a trusted signing authority, or release certification.

Create between two and five UTF-8 JSON checkpoint files with owner-private
permissions (0600), each containing exactly `unsigned_generations`,
`signed_generations`, `receipt`, and `sha256`. The SHA-256 pins must come
from custody independent of the receipts themselves. Every historical
checkpoint must extend the previous exact typed generation prefix by one.

Run:

```sh
python -m skeleton app audit-mixed-library-epoch-receipts \
  --checkpoint-file /private/checkpoint-2.json \
  --checkpoint-file /private/checkpoint-3.json \
  --trusted-local-operator
```

The application rejects symlink ancestors, symlink or hardlink file aliases,
world-writable checkpoint files, oversized input, reused paths, changing
inodes, malformed JSON, duplicate keys, missing pins, replay forks and
inconsistent signer-policy custody. It rereads each bounded file before
starting canonical full-game replay. Existing `--checkpoint` inline JSON
remains supported but cannot be mixed with `--checkpoint-file`.

A successful result means point-in-time original-game source replay and
historical private-receipt binding only. It does not establish monotonic
rollback protection, external rights, signed executables, hardware testing,
consumer readiness, or release qualification. All security and release gates
remain mandatory.
