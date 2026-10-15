# Game building data corpora

High-scale Pareto game design patterns and game math/physics references for local-model and design use.

## Contents
- pareto/ — design patterns (core verb, fairness, era constraints, provenance, etc.)
- math_physics/ — kinematics, collision, projectiles, fixed timestep, inventory math, etc.
- Split parts (*_part_*) stay under GitHub file size guidance
- .gz versions for compact transfer

## Scale note
Literal 10 GB of unique high-quality content is not practical to generate and push without Git LFS in this environment. These corpora prioritize Pareto value (patterns that cover most design/physics needs) at the largest volume that remains repo-friendly.

## Usage
Concatenate parts if needed:
  cat pareto/pareto_part_* > full_pareto.txt
Feed to local model improvement, design bible generation, or as reference context.
All content is data-only and operator-gated for any implementation.
