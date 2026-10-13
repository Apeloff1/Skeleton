# Reviewed Game Studio export hardening

**DX-76:** The approved-game ZIP download checks actual received binary
bytes against the source-custodied SHA-256 receipt **inside the client**
before offering the file, not just the expected byte count or source hash
reported by the local backend.

**DX-77:** Original archive filenames use a correctly escaped exact
\`.zip\` suffix matcher; filenames outside the approved pattern are rejected.
The source-pinned 100-chapter story adapter keeps only its actual imported
canonical functions, avoiding unnecessary imports in the reviewed module.

**No repository tests executed in this build-only pass.** Integrity checks
operate when the user later invokes the source download.
