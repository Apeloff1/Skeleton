# Controlled container digest refresh

Skeleton treats container tags as discovery coordinates, not deployment
identities. Deployment and CI surfaces are pinned to immutable sha256 manifests.
The remaining operational problem is refreshing those manifests without turning
scheduled automation into an unreviewed repository writer.

## Control model

The Container Digest Refresh Proposal workflow is deliberately read-only to
GitHub. It checks out the current default-branch commit, inventories every
managed digest pin, resolves the current registry manifest behind each explicit
tag, applies the candidate replacements only inside the disposable runner
checkout, verifies the resulting state, and uploads a patch plus provenance
evidence.

The workflow does **not** push a branch, open a pull request, merge changes, or
hold contents/pull-request write permission. Human or separately authorized
automation must review and apply the retained patch.

This separation means a compromised registry can propose different bytes, but
cannot cause those bytes to land in the repository merely because the scheduled
job ran.

## Managed surfaces

The canonical planner scans:

- root Dockerfile;
- backend/Dockerfile;
- frontend/Dockerfile;
- docker-compose.yml;
- every GitHub Actions YAML workflow.

Additional repository-relative files may be supplied to the inventory command,
but a path that escapes the repository, resolves through a symlink, is not a
regular UTF-8 text file, or exceeds the scan bound fails closed.

Only literal tag-plus-digest references are refreshable. Dockerfile ARG
substitution is supported when the ARG has a literal value. Dynamic or
unresolved variables are rejected rather than guessed.

## Evidence chain

The planner uses four content-addressed documents.

1. **Inventory** records every exact pin occurrence plus a sha256 and size for
   each scanned source file. Repeated uses of the same mutable tag must all
   carry the same reviewed digest or inventory fails.
2. **Resolution** records the resolver identity and the freshly observed digest
   for every inventory query. The scheduled workflow computes the digest from
   the raw multi-platform registry manifest returned by Docker Buildx.
3. **Plan** binds the inventory digest, resolution digest, exact source commit,
   source preimages, and old-to-new transitions. Unchanged tags produce no
   replacement entry.
4. **Evidence** binds the plan digest to every changed file postimage and every
   exact replacement. Verification re-hashes the modified checkout.

Every document includes its own deterministic digest. Tampering with a field
without recomputing the containing digest is rejected; recomputing an
intermediate document still cannot bypass the later source-preimage and commit
bindings.

## Fail-closed application

Application refuses to proceed when:

- the checkout commit differs from the plan;
- any inventoried source file changed after inventory;
- an occurrence moved from its reviewed line;
- the expected old token is absent or ambiguous;
- a source path escapes the repository or becomes a symlink;
- an input JSON document is malformed, oversized, or uses an unsupported
  schema;
- the resolver set is incomplete or contains an unexpected image;
- a registry digest is not lowercase 64-character sha256 hex.

Writes use a same-directory temporary file, fsync, and atomic replacement.

## Scheduled proposal workflow

The workflow runs weekly and can also be dispatched manually on the default
branch. It has only contents:read permission and immutable action pins.

For each validated query it executes Docker Buildx imagetools inspect with the
raw-manifest option. The raw bytes are hashed locally, producing the exact
manifest digest to propose. The resolver does not trust a mutable digest field
from shell text or an unbounded JSON parser.

The retained artifact contains:

- container-inventory.json
- container-resolutions.json
- container-refresh-plan.json
- container-refresh-evidence.json
- container-refresh.patch

Scratch manifest bytes, query lists, and intermediate TSV files are not
retained.

## Review procedure

Before applying a proposal:

1. confirm the workflow ran from the expected default-branch source commit;
2. review each old/new digest transition and the upstream image release notes;
3. inspect vulnerability scan results for the proposed image manifests;
4. inspect the binary patch and verify it changes only expected digest tokens;
5. preserve the plan/evidence artifact with the pull request or release
   evidence;
6. run canonical Merge Readiness against the exact PR head;
7. merge only after the normal security and provenance gates pass.

A refresh must never weaken a failing CVE/security gate merely to update a
digest.

## Local operator commands

Create an inventory:

    python scripts/container_digest_refresh.py inventory --output inventory.json

Emit resolver queries:

    python scripts/container_digest_refresh.py queries --inventory inventory.json

Convert a trusted tab-separated resolver result:

    python scripts/container_digest_refresh.py resolutions \
      --input resolved.tsv \
      --output resolutions.json \
      --resolver operator-reviewed

Build a commit-bound plan:

    python scripts/container_digest_refresh.py plan \
      --inventory inventory.json \
      --resolutions resolutions.json \
      --source-commit <40-char-commit> \
      --output plan.json

Apply in a clean disposable checkout and emit evidence:

    python scripts/container_digest_refresh.py apply \
      --plan plan.json \
      --source-commit <40-char-commit> \
      --evidence evidence.json

Verify postimages:

    python scripts/container_digest_refresh.py verify \
      --plan plan.json \
      --evidence evidence.json

## Residual risks

Registry compromise remains a supply-chain risk: a registry can legitimately
serve a malicious manifest at a mutable tag. This automation therefore provides
freshness and provenance, not trust in upstream publishers. Vulnerability,
license, SBOM, image scan, and release-provenance gates remain mandatory.

A tag can also be retargeted between separate resolver runs. Each proposal binds
the one exact registry manifest descriptor observed during that run; later review should treat
the digest, not the tag, as the proposed identity.

The workflow intentionally does not sign registry metadata. If the project later
adopts publisher signatures or transparency-log verification, that proof should
be added as another input to the resolution document rather than replacing the
current sha256 and source-preimage bindings.
