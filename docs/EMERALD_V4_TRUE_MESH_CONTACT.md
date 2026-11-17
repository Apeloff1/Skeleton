# Emerald V4 — independent skinned triangle-contact acceptance

This module replaces the earlier, inadequate assumption that separated bone
capsules imply separated mesh surfaces. The V4 forms retain 719,312 triangles
and 108 weighted joints; the collision monitor evaluates real GLB geometry
after applying each selected original motion channel at each sampled time.

## Actual evidence on retained V4 assets (17 November 2026)

The operator reloaded the independently pinned V4 GLBs from the original user
packages, classified 269,919 anatomical triangles into seven high-risk regions
and evaluated paired, posed triangles with a non-approximating narrow-phase
triangle-distance test. The 449,393 remaining triangles (body, mixed skin seams,
unselected wing/root areas, etc.) are explicitly unqualified.

- Hatchling: 9 poses over ground-idle-1, ground-cuddle-1 and orbit-01; 0
  observed high-risk contact witnesses at an 8 mm margin; 6 nonlinear
  between-sample intervals unresolved. **Not full collision-free.**
- Scout: same 9 poses, no sampled contact witnesses in selected regions.
  **Not full collision-free.**
- Scholar: on the sampled ground-idle-1 initial pose, **100 actual
  triangle intersection pairs** between opposing wing membranes, plus 15,961
  pairs within the 8 mm proximity threshold. Measured intersections cluster
  near the folded-wing body centerline (approximately x=-0.06 m, y=0.745 m,
  z=0.003 m). The wing near and far meshes have source rest coordinates around
  opposite z signs (+/- 0.17 m), but their skinned idle positions converge near
  z=0. This is a real deformation/rig clearance issue requiring focused
  correction and remeasurement. Do not dismiss it by hiding a warning.
- Pathfinder and Archivist full multi-pose contact checks remain incomplete:
  complex overlapping wing bounds exceeded the exploratory runtime budget.
  The monitor fails closed when work exceeds its bounded time or pair quotas.

These facts are **observations from actual original GLBs**, not results from
mock unit tests. The independently inspected original Head/Fore/Hind/Wing
joint groups and the exact model SHA-256 pins are retained. The measured
candidate counts cannot certify every pose or every surface.

## New reviewer workflow

Use a trusted Python environment with NumPy 2.3.5 and SciPy 1.17.0 installed
from reviewed wheels. Extract the exact local Hatchling, Scout, Scholar,
Pathfinder or Archivist V4 GLB from its original stage archive. Ensure its
SHA-256 matches the repository's immutable evolutionPin.json. Do **not**
load unknown network URLs, user-authored scripts from the model archive, or
activate optional equipment.

Run, for example:

    python scripts/emerald_v4_contact_scan.py \
      --model /local/original/hatchling.glb --stage hatchling \
      --output /trusted/new-receipt.json \
      --clips ground-idle-1,ground-cuddle-1,orbit-01 \
      --fractions 0,0.5,1 --margin 0.008 \
      --max-pairs 200000 --timeout 120

Then validate internal consistency of its independently saved evidence:

    python scripts/verify_emerald_v4_contact_receipt.py \
      --receipt /trusted/new-receipt.json --require-zero

The first process returns nonzero if sampled intersections are observed
(exit 2) or the sample is incomplete due to a time/pair bound (exit 3).
The second verifies the exact model and donor identity, all seven anatomical
pairs at every requested sampled pose, real counted intersections, explicit
unclassified geometry and all non-certification flags. It refuses a forged
zero-count claim or a missing interval. The consistency checker is not an
independent signed attestation of a physical capture.

## Corrective workflow and held acceptance

The near/far wing crossing is concentrated where the flight-finger chain
undergoes strong fold rotations. A corrective animation/rig pass must
preserve the existing 108-joint weighted topology and 380 original named
clips, smoothly separate membranes without creating new skin strain or
limb interference, maintain five exact growth endpoints, and demonstrate
no regression against the unchanged Hoarder. Repeated tests must span
ground-idle, cuddle, preen, flight, takeoff, landing and growth transition
states, including contact near root and farther from the centerline.

Do not transform this *sampled* surface witness into a claim of:
- continuous-time triangle/triangle CCD for nonlinear skeletal animation;
- all 719,312 triangles checked, particularly disconnected UV seams;
- safe optional equipment or clearance during growth morphs;
- AAA artistic parity with the approved poster or genuine hand painting;
- Unreal compilation, physical RTX rendering, device qualification or release.

The original Hoarder pin remains unchanged and all optional equipment remains
off. No merge or release is permitted on source-only qualification.
