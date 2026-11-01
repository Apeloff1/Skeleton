# Private pinned job files for original playable delivery

This integration provides a bounded, owner-private input format for the real
source → ZIP → fresh install → interactive moves → private save → restored
replay → independent receipt path. It reuses the canonical batch publisher,
inspector, resume, and quarantine triage implementations; it does not replace
their verification or weaken their release holds.

## Input format

Create a POSIX owner-private (mode 0600, one hardlink, no symlinks) UTF-8 JSON
file with exactly `schema` and `jobs` fields:

```json
{
  "schema": "skeleton.app.first_playable_jobfile.v1",
  "jobs": [
    {
      "source": "/owner/game-one", "archive": "/owner/out/one.zip",
      "install": "/owner/out/installed-one",
      "save": "/owner/out/one-save.json",
      "receipt": "/owner/out/one-receipt.json",
      "manifest_sha256": "<independent original source SHA-256>",
      "moves": ["up", "right"]
    },
    {
      "source": "/owner/game-two", "archive": "/owner/out/two.zip",
      "install": "/owner/out/installed-two",
      "save": "/owner/out/two-save.json",
      "receipt": "/owner/out/two-receipt.json",
      "manifest_sha256": "<independent original source SHA-256>",
      "moves": ["left"]
    }
  ]
}
```

Replace placeholders with actual independently obtained 64-character lowercase
hex digests. Keep the job file **outside all game trees and outputs**.
Do not commit private manifests, keys, saves, or receipt pins to Git.

Calculate the input file SHA-256 independently and supply it through
`--expected-jobs-sha256`. The file cannot self-attest. The same digest
must still match after the full canonical operation; any byte, inode, or
owner-custody change fails closed. Failed publication may leave immutable
partial outputs requiring quarantine; never retry by overwriting.

```sh
python -m skeleton app first-playable-jobfile \
  --jobs-file /owner/private/jobs.json \
  --expected-jobs-sha256 '<independently-held-input-digest>' \
  --summary /owner/out/cohort.json --mode publish --trusted-local-operator
```

After publication, keep the returned per-game archive/save/receipt SHA-256
values **outside the game directories**. Supply all three pins for each job
in a separate owner-private inspection job file, and supply the independently
held summary digest with `--expected-summary-sha256`. Use `--mode inspect`
for full replay or `--mode triage` for read-only quarantine classification.
Use `--mode resume` only for a contiguous, independently pinned prefix.
All modes require explicit operator authorization.

This is POSIX source-level acceptance only. It is not a Windows/macOS device
test, cryptographic signature, malware approval, rights certification,
persistent rollback protection, consumer installation approval, or release
certification. All relevant security and release gates remain mandatory.

## Read-only admission preflight

Use `--mode preflight` with an unpinned publication job file to run the
canonical source replay and check all destination names **without publishing
or reserving anything**. It checks every original project ID for uniqueness,
then repeats source verification to catch input changes. A passing preflight
is only a point-in-time admission observation: another process can occupy
the destination before publication. The actual publisher repeats all checks
at the atomic no-clobber boundaries. It is never device or release readiness.
