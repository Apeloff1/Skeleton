# Objective authoring — atomic offline playable previews

`python -m skeleton combat-objectives-author demo` performs a real
source-digest-fenced edit of the original combat objectives, runs the canonical
campaign, verifies its objective journal, and exports a portable checkpoint
package. No editable source is executed as code.

Commands:

```sh
python -m skeleton combat-objectives-author edit --source-json '<source>' --operations-json '<edits>' --expected-digest '<sha256>'
python -m skeleton combat-objectives-author verify --source-json '<original>' --receipt-json '<receipt>'
```

Bounded operations: `add-objective`, `remove-objective`, `set-points`,
`set-threshold`, `set-kind`, and `set-requires`. The editor rejects stale
source digests, unknown IDs, no-ops, invalid dependencies, budget overflow,
unsupported schemas and changes that would break canonical game compilation.
No partial mutation occurs on failure. Verification reconstructs the entire
edit transaction, objective rewards, combat replay and exported checkpoint.

Digest receipts detect drift but are not signatures or proof of authorship.
Application-level authorization, review and release gates remain mandatory.
