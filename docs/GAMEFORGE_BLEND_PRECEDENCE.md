# GameForge blend precedence repair

The ten-stage pipeline resolves blend inputs once at `execute()` entry,
instead of allowing the `detect` stage to resurrect mutable cockpit state.

- Explicit `blend` wins over a previously saved cockpit blend.
- Explicit `era` and questionnaire-selected era override the implicit blend.
- An unoverridden cockpit blend retains manual tensor-axis adjustments,
  including when the operator has rolled an oracle before generation.
- A stage may not silently revert back to cockpit blending after explicit
  inputs have been supplied.

The ARM64 regression `TestBlend.test_cockpit_blend_drives_detect` now emits
specific run/era/plan diagnostics on failure. Dedicated regression cases
cover an existing oracle, an adjusted tensor axis, and explicit-era override.
