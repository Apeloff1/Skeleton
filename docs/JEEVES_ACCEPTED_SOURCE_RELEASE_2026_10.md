# Jeeves accepted native/browser source custody — October 2026

**DX-59–63:** A complete approved browser/Godot source release can now
be independently inspected and downloaded from the *real current Studio
source tree*, not a freshly generated preview or an unapproved workbench.

- \`studio.release.catalog\` — page actual original release folder IDs from
  the active project, without claiming every folder is complete.
- \`studio.release.verify\` — validate the **canonical** dual-runtime source
  manifest and digest, exact set of files, all source SHA-256 fingerprints,
  original-world identity, matching Godot/proof JSON, reported winning
  trace, and a human acceptance record for **each current source version**.
  Requires a stable workspace revision and includes explicit lack of
  re-executed replay/device acceptance.
- \`studio.release.download\` — a separately operator-approved export
  requiring the full previous verification digest; produces a stable
  timestamps-fixed ZIP **in memory** containing exactly the approved,
  verified project sources. Server writes no ZIP or runtime binary.

**DX-64:** Browser and Godot files remain source-only, independently
reviewable and portable. Download does not imply executable Godot runtime,
store/platform entitlement, target-hardware proof, anti-plagiarism review,
shipping quality or a commercial release.

All source changes remain the sole custody of \`GameWorkspace\`.
This pass did not run any repository test suite.
