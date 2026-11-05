# Studio A — Authored quest objectives and earned player consequences

`world-quest` binds original authored objectives to the canonical world
scene graph and the actual durable `world-session` choice trace.
Quest objectives are completed only when the player reaches their scene,
has earned their required flags and has completed prerequisites.

## Author → review → compile → play → verify

```sh
python -m skeleton world-quest --store ./private propose --world-id marsh --ending resolution --title "Deliver letter" --description "Keep it sealed."
python -m skeleton world-quest --store ./private inspect --world-id marsh
python -m skeleton world-quest --store ./private edit --world-id marsh --expected-digest <quest-sha> --operation-file ./reviewed-objectives.json
python -m skeleton world-quest --store ./private approve --world-id marsh --expected-digest <edited-quest-sha> --note "Original author approved."
python -m skeleton world-quest --store ./private compile --world-id marsh --expected-digest <approved-quest-sha>
python -m skeleton world-session --store ./private new --world-id marsh --slot first
python -m skeleton world-quest --store ./private progress --world-id marsh --slot first
python -m skeleton world-quest --store ./private verify --world-id marsh
```

Typed batch edits add/replace/remove objectives atomically. Dependency
cycles, missing objectives, impossible flag preconditions and source
revision drift fail closed. Every edit revokes approval. A bounded
deterministic search produces an actual witness that satisfies all
required objectives before the specified ending; inconclusive search
is never mislabeled as a proof of impossibility.

The compiler emits a CSP-hardened offline HTML5 world player, a typed
quest handoff with replayed objective progress, and a SHA-256 receipt
binding all artifacts. The progress command reads an existing
source-leased saved player and independently replays its choices.
No unearned rewards, invented completion or silent migration is
permitted. Original-author review is not external provenance, device
testing, security certification or consumer release qualification.

Focused fixtures: `skeleton/testing/test_jeeves_world_quest.py`.
