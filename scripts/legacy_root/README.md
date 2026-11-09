# Legacy root scripts

These scripts are preserved historical/manual diagnostics that were moved out of the repository root during the September 2026 hygiene pass.

They are not part of CI or the supported project tooling surface. Several target the historical `gemini-game-craft.preview.emergentagent.com` preview service and perform mutating API operations such as build creation, force-completion, vault generation, or swarm simulations.

Do not treat them as safe smoke tests against production. Prefer maintained scripts under `scripts/` and automated coverage under the canonical test trees for current behavior.
