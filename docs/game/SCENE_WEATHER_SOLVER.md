# Weather-safe scene victory routing

The `scene-weather solve` command searches authored weather cycles, blocked
exits, collectible prerequisites, and canonical scene transitions. It returns
the shortest legal sequence of actions, a source-bound replayable terminal
checkpoint, and a deterministic state digest. It never invents items or
overrides a weather gate.

```sh
python -m skeleton scene-weather solve --demo
python -m skeleton scene-weather solve --source-json '{"schema_version": "..."}'
python -m skeleton scene-weather solve --session-json '<verified checkpoint>'
```

Provide an actual valid authored JSON source in place of the placeholder.
The solver also accepts `--max-states` (1..512, default 256) and
`--max-depth` (0..64, default 32). These bounds are intentionally separate
from the world's own step budget. `solved` means the returned
`terminal_session` has passed canonical replay verification. `unreachable`
means the bounded state graph was exhausted without a win. `inconclusive`
means a search bound was hit and **must not** be treated as unwinnable.

Checkpoint mode verifies the supplied source, event journal and parent-save
lineage before searching. A malformed JSON input, forged inventory, unknown
weather condition or altered receipt fails closed. Digests are integrity
checks, not authentication or authorship signatures. No network, provider,
filesystem write or external game content is needed.
