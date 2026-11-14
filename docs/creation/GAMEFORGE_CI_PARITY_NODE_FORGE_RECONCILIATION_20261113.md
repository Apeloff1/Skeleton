# GameForge integration CI repair — exact-head source/parity and node-forge security

Source candidate: PR #5321 head `58988790fb6ee864377c88a734a45d00c2f63236`.
This repair is additive on the existing integration branch; it does not merge,
release, suppress CI, remove hold labels, disable checks or change main.

## Confirmed exact-head failure evidence

- GitHub job 132179948253 (Jeeves public game-quality source qualification)
  failed during `python scripts/check_ai_file_tree.py`, before evaluator tests.
- Job 132179948954 (local inference/delivery) stopped on the exact same
  canonical AI-tree parity check.
- Four reported parity errors: missing mirror
  `skeleton/ai/runtime/context/galaxy_profile.py`; missing
  `skeleton/ai/forge/playable_provenance.py` and
  `skeleton/ai/forge/playable_tuning.py`; unequal AST contents for
  `skeleton/ecs/test_script_runtime.py` vs
  `skeleton/ai/runtime/ecs/test_script_runtime.py`.
  The ECS discrepancy consisted of divergent import-module paths in a test
  file; the canonical tracked source is restored as an exact mirror, instead
  of masking the validator or downgrading its semantic checks.
- Job 132179949365 (App Foundation E2E) stopped while building the frontend
  Docker image. `patch-node-modules.js` rejected resolved
  `node-forge@1.4.3` with `requires security patch review`.
  No Playwright cases ran; the test was not an E2E behavioural failure.

## Security review and provenance

The previous reviewed compatibility patches for node-forge 1.4.0/1.4.2
remain unchanged. node-forge 1.4.3's upstream `lib/rsa.js` uses
`_encodeDigestInfo` to re-encode with/without NULL parameters, comparing
the canonical DER bytes before trusting the signature. It must not receive
the earlier patched nested-arity conditional because its parser structure
is different.

The 1.4.3 path now accepts **only the exact canonical upstream Git blob**
`65f6e8469d8a7695f4438722577230136f9dd425` from
`digitalbazaar/forge` tag `v1.4.3` and verifies unique required code
anchors. It never waives the existing installed-library malicious-signature
negative fixture in `verify-no-release-npm-security.js`, which now
recognizes the same pinned canonical-DER source as an alternative to the
1.4.0/1.4.2 patched-arity source. Unknown versions, diverged code and
failed signature regressions **fail closed**.

The tagged upstream commit/blob was inspected in the connected GitHub
source; the npm lockfile already resolves 1.4.3. This is not a claim of
full supply-chain or cryptographic certification.

## Required final-head verification

1. `python scripts/check_ai_file_tree.py`
2. `python -m compileall -q skeleton/context skeleton/ai/runtime/context skeleton/forge skeleton/ai/forge skeleton/ecs skeleton/ai/runtime/ecs`
3. `cd frontend && yarn install --frozen-lockfile --ignore-scripts && node scripts/patch-node-modules.js && node scripts/verify-no-release-npm-security.js`
4. Run the focused Jeeves quality and eight-native-scene regressions and the
   full frontend typecheck.
5. Recheck **all** exact-final-head Merge Readiness, App Foundation E2E,
   security, native/device and source-contract checks; pending, skipped,
   cancelled or ancestor results do not qualify. Do not merge or release.
