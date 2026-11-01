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


### 2026-11-01 lexical path and output-pin custody repair

Single-game delivery now collapses lexical dot segments with `os.path.abspath`
**before** source/install/output disjointness checks. An existing sibling
followed by `..` can otherwise disguise a destination inside the original
source tree without using a symlink; descriptor-relative nofollow alone does
not reject such an alias. Symlink resolution remains forbidden and delegated
to the descriptor-anchored source and destination openers. The batch path
already normalizes lexical aliases and now rejects empty, uppercase, truncated,
or non-hex optional output pins before publication or resumed delivery.

Focused regression entrypoints (not a test result):
`python -m pytest skeleton/testing/test_app_offline_first_playable_delivery.py skeleton/testing/test_app_offline_first_playable_batch.py -q`.
No device, signing, rights, malware or release qualification is asserted.

Read-only interrupted-cohort triage also reopens each artifact parent after
its nofollow descriptor-relative existence check, **including missing names**.
A replaced parent must yield `unsafe_custody_quarantine`, not a false
`missing_unpublished` state that could be mistaken for resume eligibility.
The diagnostic still does not reserve names, repair outputs, or certify release.

The canonical standalone ZIP publisher now applies the same lexical path
normalization before its source/archive containment check. Without it,
`existing-sibling/../original-source/unsafe.zip` could bypass the source
containment guard even though each opened component was not a symlink.
Source and destination still require descriptor-anchored ownership checks;
no archive or game source is rewritten on rejection.

## Independent cohort pins and interrupted-delivery recovery

The batch inspector, resume path, private job-file bridge, and quarantine
triage share one strict 64-character lowercase SHA-256 pin validator.
A literal backslash followed by `Z` is **not** a digest terminator and must
never be required or accepted. All three archive/save/receipt pins must be
supplied for an already published game; a partial triple is rejected. Fresh
publication cannot use output pins as authority, and each original manifest
pin is validated before destination or source I/O.

A successful single-game replay does not permanently certify a multi-game
cohort. During publication and resume, the publisher replays **every**
original source after the final game has been installed and again after
the summary receipt is published. It compares each source against its
initially admitted result and pinned source-root identity. If an earlier
source changes while a later game is being delivered, the cohort fails
closed and does **not** issue a successful summary. Already published
files remain in place for operator quarantine; no pathname rollback or
unsafe overwrite is attempted.

Read-only triage only reports `resume_eligible_with_independent_pins: true`
when the previously published prefix has valid independent replay pins,
the suffix outputs are absent, the summary is absent, **and** the remaining
original sources pass replay and no-clobber destination preflight.
`resume_source_preflight_verified` records that point-in-time check;
`resume_destinations_reserved` remains false. Duplicate original project
identities, changed source manifests, occupied destinations and failed
source custody turn eligibility off. This is not a lock, reservation, device
qualification or release authorization. The subsequent resume repeats its
own admission and publication checks.

Focused regression entrypoints (execution still required):

```sh
python -m pytest -q \
  skeleton/testing/test_app_offline_first_playable_pin_contract.py \
  skeleton/testing/test_app_offline_first_playable_batch.py \
  skeleton/testing/test_app_offline_first_playable_batch_triage.py \
  skeleton/testing/test_app_offline_first_playable_jobfile.py
```

The source-level evidence never implies Windows installation, native Godot
execution, trusted publisher signatures, rights clearance, hardware
qualification, or production release certification.


### Original source-root continuity during read-only cohort preflight

The preflight path now pins every source-root filesystem identity before
canonical replay, checks each root immediately before and after its replay,
and checks all roots again after the second cohort-wide replay. An attacker
cannot substitute an identical-byte source root between games and obtain a
stable-source preflight receipt. This is a point-in-time read-only custody
check; it does not reserve outputs, lock source directories, qualify hardware,
or grant release, signing, or rights approval.


## Opt-in original-source provenance during read-only inspection

An independently pinned delivery summary proves installed-source/archive/save
replay, but it does **not** prove that the original authoring workspace still
exists. To require that additional custody property, supply
`--verify-original-sources` together with `--mode inspect` and the already
required independent job-file, per-game output and summary digests. The
canonical inspector replays every original source, checks each against the
installed project's world and identity, and rechecks source-root inode custody
after replay. Missing, replaced or modified original sources fail closed.

The option is deliberately rejected for publication, resume, triage and
preflight, and does not create or repair files. Without the option, a fully
pinned archived delivery remains inspectable even if its original authoring
workspace has been intentionally retired. Neither mode certifies rights,
native devices, signed packages, persistent rollback protection or release.

Focused acceptance (must be executed before promotion):
`python -m pytest -q skeleton/testing/test_app_offline_first_playable_jobfile.py skeleton/testing/test_app_offline_first_playable_batch.py`.
