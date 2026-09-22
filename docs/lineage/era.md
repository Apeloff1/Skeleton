# Era Bind (GB-39)

Parent #80. Like-titles resolve to HOUSE_ERA. Forge without citation is illegal.

## Public card

- `era_bind.resolve(vision)` → `{title,era,citation,url}`.
- `plan` / `cut` / `speak` share the resolver.
- `GameForgeRun.execute` stamps `reference` + `reference_card` even when `project_root` is None.
- Does not edit operator deck organs.

## Accept

`forge("extraction")` has citation + reference + stored_prose==0.

cut then plan sees the bound era.
