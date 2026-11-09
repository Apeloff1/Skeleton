# Unit collection and verified multimodal admission repair — 2026-10-15

## Actual failing gate

The exact-head GitHub Merge Readiness **Unit** job reported 17 import-time collection errors on 15 October 2026. Most arose from `skeleton.ai.runtime.learning_foundation.multimodal` importing a deleted byte-pattern contract and a missing verified-asset class from `skeleton.ai.runtime.multimodal.intake`. The governed corpus additionally expected a staged asset registry and the source byte length alias that the underlying intake had lost.

This repair restores the original **fail-closed meaning** instead of adding symbolic placeholders:

- The full-text training-export scanner uses byte-compiled copies of the existing instruction-detection pattern. Document bytes are checked even beyond the bounded prefix intake scan, without granting model authority.
- The canonical intake maintains a bounded per-asset registry. Two sources with a reused asset ID but conflicting bytes or metadata are rejected.
- The verified asset extends the immutable sanitized asset with a real strict decoder `MediaValidationReceipt`; it only accepts actually supported image/PCM WAVE formats from the existing `verified_intake` and `media_validation` owners.
- Reverification recomputes both the actual source byte hash and strict decoder measurements under the issued limits. Content and metadata cannot become trusted instructions or automatic training authorization.
- Rejection of corrupt media does not publish a fake verified asset.

The Merge Readiness Unit setup now installs the existing pinned `Pillow>=12.3.0,<13` optional image decoder dependency, required by a real video-evidence fixture. The training lock-order regression now constructs actual source-fenced `DatasetRegistry`, `TrainingRepository` and `ReferenceLocalTrainer` objects through the existing governed training fixture instead of importing nonexistent helpers from a different test module.

`skeleton/testing/test_multimodal_intake_learning_compatibility.py` adds native safe-media tests for full-text instruction detection, governed registry mutation, real WAV receipt issuance, source tampering and publication rollback.

**Boundary:** CI still must execute the updated tests before any green Unit claim. These repairs are source updates and do not run game ROMs, validate AI weight improvement, or promote unreviewed media knowledge.
