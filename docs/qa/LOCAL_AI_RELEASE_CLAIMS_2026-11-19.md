# Local Jeeves Docker — independent signed release-claim custody

This is a VERIFY-ONLY building block for standalone local AI provenance.
It never creates a signing key, signs an artifact or grants automatic
merge/release authority.

## Trust boundaries

Two different Ed25519 public keys are required: one held by the security
review authority, the other held by the release authority. Both are
obtained independently of the evidence bundle, are pinned by the operator,
and must not be contained inside that archive. The two PEM files must
contain different public keys.

The evidence root must be owned by the invoking operator with 0700
permissions. It contains exactly these three private files:

- release-claims.json — strict canonical UTF-8 JSON, sorted keys and one
  trailing newline.
- security.ed25519.sig — 64 raw Ed25519 signature bytes.
- release.ed25519.sig — 64 raw Ed25519 signature bytes.

A correct signature binds the exact manifest bytes to the two public-key
identities, and the manifest binds its source_head (exact Git SHA), the
complete independent offline image receipt SHA-256, model digest,
Compose/physical GGUF/guarded chat/writer epoch/recovery/device/WSL2
receipt hashes, SBOM, reproducible build and exact-head CI matrix.

The signer must independently obtain and physically qualify each referenced
receipt. A digest field in a signed manifest is a claim, not automatic proof
that its cited check was performed.

The verifier checks all of the following before admitting the claim:

1. Both external public keys are distinct, regular, owner-owned PEM files,
   not symlinks and not located under the untrusted evidence directory.
2. The folder has no unexpected file and has strict owner permissions.
3. The JSON file and signatures are regular, owner-private, single-link
   files within strict size bounds; no path following or duplicate JSON
   keys, non-finite values or extra fields are allowed.
4. The full source SHA and independent image receipt SHA-256 match operator
   expectations, and all other evidence digests are lowercase 64-hex.
5. Every authority flag in the signed manifest is explicitly FALSE:
   release, protected chat and coherent recovery.
6. The system OpenSSL Ed25519 verifier approves BOTH detached raw signatures
   over the exact canonical manifest byte file. No shell interpretation,
   subprocess stdout, private key or raw diagnostic is exposed.
7. The manifest bytes are independently rechecked after verification.

## Read-only operator command

    python scripts/local_ai_docker.py verify-release-claims \
      --directory /home/operator/private/release-evidence-001 \
      --security-public-key /home/operator/trust/security.pub.pem \
      --release-public-key /home/operator/trust/release.pub.pem \
      --expected-head EXACT_40_HEX_COMMIT \
      --expected-image-receipt-sha256 INDEPENDENT_64_HEX_RECEIPT

The output states that independent cryptographic signatures were verified,
but also states that referenced physical receipts were NOT validated by
this verifier and that release_authorized and merge_authorized are FALSE.
A self-generated key in the archive is never a trust anchor.

The public keys must be provisioned through separate administrative
trust channels; do not store signing private keys in the repository,
a Docker image, model archive, public CI artifact, user transcript or
application volume. Use a physical/restricted signing procedure outside
this verifier.

## Remaining release gates

- Exact-head mandatory repository CI, source/identity and security gates.
- Real four-service production Docker and licensed GGUF execution on the
  actual target device, with no hosted provider and no registry pulls.
- Independent active tokenizer, bounded reviewer and protected-chat
  request/response proof.
- Majority-durable shared Mongo writer epoch, actor migration and external
  writer exclusion.
- Coherent Mongo/SQLite/Chroma snapshot and isolated database-level restore.
- Physical GPU/CPU pressure, WSL2/Windows device, restart and recovery proof.
- Review approval under the repository's exact-head ruleset.

Never treat a signed manifest or source-level test as sufficient evidence
for these physical and trusted-authority stages. Keep the PR draft until
independent review and release ruleset authorization.
