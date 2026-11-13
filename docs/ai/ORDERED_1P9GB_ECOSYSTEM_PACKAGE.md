# One ordered 1.9 GB AI ecosystem package — source-bound, release-held

The builder at `scripts/build_ai_ecosystem_bundle.py` emits **one** uncompressed,
self-contained, stream-verifiable `.tar` containing the Git-tracked canonical
`skeleton/ai` source and explicitly approved local model/data artifacts.
It **does not** create filler bytes, trust model-supplied approval, download
weights, alter the source tree, or put the binary in Git. It cannot produce a
qualified 1.9 GB package until real approved bytes are supplied.

## Mandatory construction and archive order

The ordered stage map comes from `machine/ai_master_build_sequence.json` and the
conservative source classifications in `machine/ai_ecosystem_bundle_v1.json`.
Unclassified new AI paths **block** packaging until assigned an explicit stage.

| Stage | Contents | Blocking prerequisites |
| --- | --- | --- |
| MBW-00 | Identity, contracts, serialization, primitives, architecture | none |
| MBW-01 | Durable state, transaction/outbox, recovery | MBW-00 |
| MBW-02 | Inference, model weights, memory, context, retrieval | MBW-00/01 |
| MBW-03 | Policy, tool security, delegated action gates | MBW-00/01 |
| MBW-04 | Jeeves, agents, planning, bounded cognition | MBW-02/03 |
| MBW-05 | APIs, product, observability, game studio surfaces | MBW-01/03/04 |
| MBW-06 | Research, forge, evaluation, controlled learning | MBW-02/03/04 |
| MBW-07 | Build, native/distributed, installer and hardening | MBW-05/06 |

The complete graph and work-package ownership are stored in the archive manifest;
its byte order is MBW-00 through MBW-07. **Archive order is not execution
attestation**: qualification still requires independent stage acceptance,
signed accountability, and successful exact-head CI/security gates.

## Byte and provenance policy

Target is **1,900,000,000 decimal bytes** (1.9 GB). Publish only when the actual
tar size is 1,880,000,000–1,920,000,000 bytes and its real payloads total at
least 1,850,000,000 bytes. No silent split, byte padding, thin-pointer-only
model substitute, approximate metadata count, or sparse-file fake size.
The actual tar size includes headers and the final canonical manifest.

The operator must provide an offline payload directory (outside the repo), with
`approved_artifacts.json`, one or more real approved model files, and any
additional explicitly licensed original dataset/runtime assets. Each entry
requires exact `bytes`, lowercase SHA-256, license, provenance, destination,
canonical wave, and `rights_approved: true`. Missing or mismatched records hold
the entire bundle. Models must be at MBW-02; research datasets can be MBW-06.

Example ledger structure (**replace all values with real verified data**):

```json
{
  "schema_version": 1,
  "artifacts": [
    {
      "file": "weights/operator-installed-model.gguf",
      "destination": "models/operator-installed-model.gguf",
      "wave": "MBW-02",
      "bytes": 1790000000,
      "sha256": "REPLACE_WITH_REAL_LOWERCASE_SHA256",
      "source": "operator-owned:checkpoint-and-provenance-record",
      "license": "REPLACE_WITH_VERIFIED_MODEL_LICENSE",
      "rights_approved": true
    }
  ]
}
```

Example sizes are illustrative, not an inventory claim. Adjust actual model
selection so source + artifact bytes and tar headers fit the 1.9 GB window.

## Build, verify and publication

On Linux with a clean checkout at the intended exact source SHA:

```bash
python scripts/build_ai_ecosystem_bundle.py build \
  --repo-root . \
  --payload-root /path/to/approved-offline-ai-payload \
  --artifact-ledger approved_artifacts.json \
  --output /mnt/artifacts/skeleton-ai-ecosystem-1.9gb.tar

python scripts/build_ai_ecosystem_bundle.py verify \
  /mnt/artifacts/skeleton-ai-ecosystem-1.9gb.tar
```

Both operations are fail-closed. Source files come from `git ls-files` only.
Parent directory traversal and symlinked inputs are refused using descriptor-
anchored `O_NOFOLLOW` opens. Source mutations are detected by descriptor metadata
and closed after reading. SHA-256 is computed over the exact bytes written,
then the output is independently re-streamed and checked against the manifest.
The output is published atomically and without overwrite only after verification.
No extraction of untrusted archives is required for verification.

**Operational holds:** provenance declarations still need independent audit;
source and weights alone cannot certify a runnable installed product, model
quality, security, authorization, device compatibility, or rights. The tar
manifest marks itself `content-only-no-release-attestation` and the verifier
reports `integrity-verified-not-release-certified`. Do not mark any release,
installation, signed completion or mandatory CI job green from packaging alone.
