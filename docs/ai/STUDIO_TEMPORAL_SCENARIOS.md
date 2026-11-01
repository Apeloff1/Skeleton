# Studio A — Source-leased temporal scenario comparisons

The operator can start with an existing temporal-window authoring document,
compare deterministic deadline alternatives, save an immutable private receipt,
restore it against the exact source digest, and select only a canonically
accepted variant for the existing HTML5 playable director handoff.

Run the CLI as a module, supplying the current project source digest and
canonical temporal baseline authoring. Use `--prompt` for deterministic
tight/buffered proposals, or `--candidates` for an explicit bounded array
of `{"id": "variant-name", "authoring": {...}}` objects. Add
`--select variant-name --playable-manifest` for an accepted handoff,
`--publish PRIVATE_DIRECTORY` for no-overwrite custody, and
`--restore PRIVATE_DIRECTORY` with the exact source digest for replay.

The static Jeeves tool `studio_original_temporal_scenarios` accepts the
same typed inputs. It never executes user-supplied Python, dynamically imports
tool names, calls an inference provider, or writes files.

Rejected scenarios carry no playable eligibility. All accepted scenarios
must preserve project, source, quest and session identity. Receipts are
recomputed on replay, bound to the exact canonical source, size-limited,
private, nofollow, and never silently overwritten. Operator ticks are
estimates; native timing and consumer-device qualification remain held.
