# Emerald V7 — original Three runtime process custody

**Review-only.** This repair strengthens the operator that performs actual Three.js 0.186.1 mixer playback and independent 365,997-vertex contact analysis on the exact SHA-256-pinned Pathfinder and Archivist V7 GLBs. It changes no model bytes, active application assets, installer, runtime model pin or release status.

## Source of the defect

Prior `scripts/run_emerald_v7_real_three_qualification.py` checked the Node version string and the source files, but not the concrete Node executable itself. The child runner wrote stdout/stderr to `TemporaryFile`, bounding Python memory but allowing an uncooperative or compromised child to fill the operator's scratch disk before its wall-clock deadline. This is unacceptable for an original-binary qualification process.

## Revised executable and child-process admission

- Resolve the actual executable from the explicitly provided `--node` path or the caller's trusted `PATH`; require a regular executable of bounded size and reject an executable that is itself a symlink. Its **entire SHA-256** and byte count are captured before work.
- Launch **that specific executable path**, not a re-resolved command name, and require the independently observed Node 24 version. Version identity is only a compatibility check, not proof of authenticity.
- Pass an allowlisted, sanitized environment: no inherited `NODE_OPTIONS`, `NODE_PATH`, `PYTHONPATH`, package-manager preloads, GitHub credentials, proxy variables, runtime preload flags or miscellaneous host environment.
- Run each child with `shell=False`, `stdin=DEVNULL`, separate stdout and stderr pipes, 64 KiB streaming readers and **16 KiB maximum retained tail per stream**. Output is never accumulated without a bound in Python memory or in temporary log files.
- Set a **hard 8 MiB per-stream output budget**. Exceeding the budget terminates the source child and refuses the qualification; a child with nonzero exit code or an expired bounded wall-clock deadline also fails. POSIX creates an isolated process session and terminates its entire process group, preventing escaped grandchildren from keeping pipes alive. On Windows, the direct process is terminated; further process-tree isolation requires an independently qualified Windows job-object runner.
- Rehash the Node executable, reviewed original geometry modules, source scripts, and installed Three `three.core.js`/`three.module.js`/`package.json` after **both** original stage runs, in addition to the full 229,515,688 model bytes. A change in any source fingerprint fails before the final acceptance directory is published.
- A successful operator-produced receipt now includes the full Node executable SHA and byte count. It still marks `independent_runtime_binary_signature_attested: false`: a hash is a custody record, **not** an independent signed operating-system provenance certificate.

## Focused regressions

`scripts/test_run_emerald_v7_real_three_qualification.py` now tests **real subprocesses** (not inert mock objects) for shell-free literal arguments, nonzero exit, timeouts, large streaming output, forced termination on an exceeded output quota and bounded retained output tails. It exercises a regular executable versus a symlink/nonexecutable entry, checks the exact SHA of the selected runtime binary, and ensures that a binary mutation during the run prevents a final positive receipt.

Other existing regression checks preserve source-case holds: missing or forged original V7 GLBs, withheld second stage, altered Three/geometry source hashes, compromised paired JSON, symlinked or existing destinations, timeout, skipped poses, nonzero contacts and all prohibited product acceptance flags.

The operator must be invoked only with verified source files, the reviewed five-tool contact archive and an explicitly trusted Node binary. The 108-pose Three/triangle execution remains **pending** until a source-qualified machine actually runs both original V7 GLBs and publishes two independent contact reports. Earlier synthetic tests are not that execution.

## CI and publication limits

The source stack has queued/completed GitHub workflow *records*, but several new workflows are jobless on the feature branch and are **not qualifying source CI passes**. The valid exact-head source, Windows, security and release gates must be observed independently after the appropriate repository review. Binary publication drafts still do not contain all eight real 32-MiB-or-smaller original Git blob segments.

No source change or local executable hash clears 415,154 previously observed near-margin sampled triangle occurrences, 59,508 inherited attachment seams, continuous-time skinned collision, arbitrary browser playheads, actual WebGL/device qualification, artist/approved-poster fidelity, Unreal/physical RTX, merge or release.
