# Read-only original source signing request

`python -m skeleton app source-signing-request --archive PATH
--expected-archive-sha256 PIN --expected-manifest-sha256 PIN
--trusted-local-operator` verifies an original offline game ZIP against
**independently distributed** archive and manifest SHA-256 pins.

The CLI produces the exact domain-separated message bytes (hex) and their
SHA-256 digest for a separately controlled Ed25519 signing authority. This
request can be signed externally and the detached 64-byte signature can be
verified with `verify-archive-signature` using a separately pinned 32-byte
public key. No private key is loaded, stored, exported, or invoked by this app.

The source archive is inspected twice under descriptor-safe custody and its
inode identity is fenced. Any change fails closed. No file is written by the
request operation. A signing request is not a signature, native package,
publisher identity proof, legal rights grant, or device qualification.
Consumer release and all existing CI/security gates remain held.
