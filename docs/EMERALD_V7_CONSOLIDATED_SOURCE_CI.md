# Emerald V7 — unified exact-head source CI without false binary or device approval

The review-only Emerald V7 stacked branches carry multiple historical source and asset workflows, but many **push-triggered runs** have been reported as failed without a single associated job. Such administrative workflow failures cannot serve as source-test evidence. They must not be counted as either successful execution or a reproducible source-code failure until actual job logs exist.

This draft adds one **pull-request-only** and manually dispatchable `.github/workflows/emerald-v7-exact-source.yml` for a complete, exact-head source qualification of the current V7 Three integration and its independently reviewed original model identities. It does **not** alter the original Dragon Atelier workflow, remove other CI holds, grant write permissions, or merge any PR.

## Parallel exact-head jobs

| Job | Actual code exercised | Evidence boundary |
| --- | --- | --- |
| Original source pins | Complete source pin manifest checks, 109-node/108-skin-joint target/census fixtures, independent GLB/ZIP receipt identity and SHA negative tests | No actual 114–115MB original GLB mounted |
| Real Three synthetic mixer | Actual Three 0.186.1 `THREE.AnimationMixer`, six 0.22-second transitions and 108-bone synthetic noncontiguous skin fixture | Genuine Three runtime on synthetic bones, **not** the original models or physical WebGL |
| Python geometry/operator | Actual source-level validators, hostile checkpoint remeasurement, two-stage GLB admission, bounded subprocess logging, independently revalidated JSON receipt and all non-release flags | Numerical and mocked source fixtures; original GPU, real two-model collision run and full CCD not executed |

Each job checks out `github.event.pull_request.head.sha` explicitly and verifies that `git rev-parse HEAD` matches. The workflow has **read-only repository permissions** and `pull_request` path filters scoped to V7 source/evidence files. Node and Python dependencies are pinned with package lifecycle scripts disabled for the isolated Three test. Cancellation groups prevent superseded review-head work from accidentally being counted as current acceptance.

The three parallel jobs have no dependency on remote GitHub upload of the eight 32 MiB source-model chunks and do not smuggle simulated results into actual model acceptance. Even if green, original 229.5MB GLB publication, real source-mesh Three pair execution, arbitrary playhead timing, continuous skinned collision, other anatomy, WebGL/device, artist poster fidelity, original Unreal, physical RTX, security, provenance and release remain separate mandatory holds.

**Status at authoring:** exact-head source workflow created on a review branch. Passing GitHub results must be confirmed from this branch's actual workflow jobs; no green checks are inferred from the YAML alone.
