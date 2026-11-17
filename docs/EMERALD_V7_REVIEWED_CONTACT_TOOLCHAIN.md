# Emerald V7 verified original geometry-source staging

The original V7 crossfade scanner requires five separately reviewed Python tools. Four are inside the previously retained **source-and-contact-evidence.zip** archive, while `analyze_seams.py` is in the separate **pathfinder-v6-tail-clearance.zip**. Reconstructing that tool directory manually could accidentally mix revisions and bypass contact-witness provenance.

This branch adds `scripts/prepare_emerald_v7_reviewed_tools.py`, a byte-exact offline source-only stage. It verifies **both entire retained archive SHA-256 digests**, enforces archive length and ZIP quotas, checks the entire member directory for encrypted, duplicate-case, linked or traversal entries, extracts *only* the five explicitly reviewed Python file members and rejects even harmless-looking changed bytes. All five files are independently rehashed, written in a new exclusive staging directory with a `source-custody.json` receipt, and marked read-only. It never reads, writes, extracts, or publishes the 114 MB model inside the V6 archive.

| Original archive | Exact size | SHA-256 |
|---|---:|---|
| source-and-contact-evidence.zip | 60,591 bytes | `fc5b15192353c28af7af1d7a8af7762c3c1207d46d3cb14df01e5809c9004cda` |
| pathfinder-v6-tail-clearance.zip | 114,764,553 bytes | `7fb92f1fe2b5e14c7fbae2a631a190ead4087f8f0888eb83dd2b2a505a7d0773` |

**Tool pins**: `contact_audit.py` (23,471 bytes, `0333ec4e01f701554e6f62b443fc5b2283bb68e8a62aaf324760068cc7107d4f`); `contact_geometry.py` (`ab08763903de7d222881e69cd1f8dc14e0c2f67be8c0ff22a15164f55bb132f5`); `contact_geometry_accel.py` (`fd5bd4c28ff528e3be7e0500476c27e52f054a0ef9ff34fa9ec9294d4800e431`); `fast_wing_witness.py` (`e170a70ec2522ef4a162ef53c8d3aabcf2a3ce110dc7fbeadca8852480845187`); `analyze_seams.py` (`482391dd5a68ad36411a315aab7abcb0b70febbca3dc780fb217f6f4fd32dc1a`).

## Deterministic offline operator staging

```sh
python scripts/prepare_emerald_v7_reviewed_tools.py \
  --contact-archive /trusted/source-and-contact-evidence.zip \
  --v6-archive /trusted/pathfinder-v6-tail-clearance.zip \
  --output /unused/evaluation-contact-tools
```

The output directory must **not already exist**. Only the five verified Python files and `source-custody.json` appear; no transitive unreviewed dependencies, shell scripts, model binaries or executable archive hooks. Never run this on ZIP files with altered pins, under a writable untrusted parent, or over an already staged original tool directory. This is a custody-control tool; a non-cooperating filesystem writer can still require independent OS permissions/locking.

The staged path can then be passed to:

```sh
python scripts/emerald_v7_crossfade_screen.py \
  --stage pathfinder --steps 9 \
  --model /verified/pathfinder-v7.glb \
  --source-tools /unused/evaluation-contact-tools \
  --checkpoint /new-evidence/pathfinder-progress.json \
  --output /new-evidence/pathfinder-crossfade.json
```

Use an independently pinned Archivist model and separate fresh checkpoint for the other stage. This runner still checks every tool hash again before importing it. It does not authorize temporary network access, browser scraping, native Unreal import, RTX rendering or arbitrary code execution by the staging command.

## Explicit holds

Stage success only proves original *tool bytes*, not that all runtime paths, arbitrary loop phases or **continuous** skinned collision intervals were tested. The 108 sampled V7 poses remain restricted to three anatomical pairs; 415,154 near-margin occurrences and 59,508 inherited shared-vertex contact occurrences remain unresolved. Full artist approval, true hand-painted textures, original binary GitHub publication, actual Three.js browser/device, Unreal RTX and independent release qualification are still held. No automatic merge, equipment enablement or release.
