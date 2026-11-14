# Expanded GameForge genre catalog — 13 November 2026

## Audit result

The historical GameForge creator questionnaire carried 16 genre chips before PR #5296,
while its `BRIEF_ERA_VOTES["genre"]` registry recognized 36. This was **not**
the number of supported game concepts across the Skeleton/Galaxy ecosystem.
The broader Galaxy production questionnaire has 14 production matrices, nine
style selectors and 100 extended controls, but these are **not** genres.

This follow-up adds a **158-choice** grouped and searchable GameForge genre
intake, with **122 new genre/subgenre labels** plus the original 36 preserved
bit-for-bit in their canonical era votes. The 11 groups are:

1. Action & shooting
2. Role-playing & progression
3. Strategy & tactics
4. Simulation & management
5. Adventure & narrative
6. Platform & exploration
7. Puzzle & tabletop
8. Horror & suspense
9. Racing, sports & vehicles
10. Creative, social & rhythm
11. Arcade & casual

## Source and interface contracts

- `skeleton/context/genre_catalog.py` is the authoritative genre and era-vote
  registry, including stable IDs, group descriptions, and read-only response.
- `skeleton/context/questionnaire.py` uses the complete registry; all prior
  36 mappings are unchanged and its 12-beat design system takes precedence.
- `GET /api/skeleton/genres` returns the current grouped registry and mapped
  era IDs without a network provider or gameplay side effect.
- `frontend/src/skeletonForge/genreCatalog.ts` is the offline UI mirror.
  A Python parity test fails if any genre ID is missing, duplicated, or
  reordered; the frontend ships all choices even without API availability.
- The creator brief renders 36 familiar choices by default and provides
  category browsing and whole-catalog search for the full 158; selections
  survive review and the existing `/api/skeleton/run` contract.
- Generated source manifests, model runtime, Godot exports, security policies
  and build-plan receipts are not bypassed or relaxed.

## What the catalog does and does not guarantee

A **genre** is a creator's design classification. An **era** is an existing
canonical compilation target; multiple genre labels intentionally vote for
the same era. A **playable genre implementation** needs distinct original
mechanics, content, verification, and device-backed run proof.

This change makes 158 design concepts *selectable and mechanically classified*
for GameForge intake. It **does not** assert 158 unique gameplay engines,
158 independently qualified Godot projects, or complete arbitrary genre
simulation. Several labels (racing, fishing, rhythm, social deduction,
management) currently map to the closest existing era and require dedicated
runtime engines before promising full native fidelity.

## Qualification and migration

- Keep historical token normalization and 36 genre mappings stable.
- Validate all 158 token/era associations against `list_eras()`.
- Run `skeleton/testing/test_extended_genre_catalog.py` and existing
  `skeleton/testing/test_questionnaire_brief.py`.
- Run the frontend questionnaire/instruments tests and static typecheck.
- Confirm app navigation, instrument accessibility, backend request/response,
  genre search/group filtering, auth, and source provenance.
- Require exact-head CI, security, mirror, frontend, Godot and backend
  qualification before promoting any release. Skipped/cancelled is not passed.

## Remaining higher-level integration

Durable, project-scoped cockpit steering and a fully typed handoff between
Galaxy's 14 matrices/100 sliders and the GameForge design tensor require a
separate reviewed migration. Neither frontend controls nor genre taxonomies
should be falsely counted as runnable engine capabilities.
