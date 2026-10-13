# Jeeves actual Universal Forge game-source production — 2026-10

**DX-78–82.** A real source-production adapter has been added to the
installed Universal Forge. Rather than claiming that a diagram executes a
game, \`studio.forge.plan\` validates *real* installed component kinds,
typed inputs and outputs, allowed graph wire endpoints and cycle conditions
through the canonical Universal Forge.

\`studio.forge.stage\` requires that exact review receipt and deliberate
designer authority before staging a typed original \`assets/forge/<id>.json\`
blueprint into the current GameWorkspace.

**Crucial:** Canonical GameWorkspace now reruns the same installed Forge
validation at **both** the source proposal **and** human commit boundaries.
This prevents a graph edited after planning from silently bypassing the
installed typed ports, kind registry or blueprint source digest.

\`studio.forge.verify\` reads the actual current project version and
validates it against the installed component registry without creating a
second runtime or implying an asset was already exported.

This makes original Forge blueprints real editable project sources, but
does not run a native game, execute unknown plugins, train a model or
grant general filesystem modification rights.

No repository tests run during this build-only implementation pass.
