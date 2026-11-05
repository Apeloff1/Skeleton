# Local studio source discovery

The studio CLI now supports reproducible, bounded queries without external
providers:

```sh
python -m scripts.studio_ecosystem_cli --search arena_fighting --limit 12
python -m scripts.studio_ecosystem_cli --search "illegal match-rigging cartel" --deep-search
```

Metadata search reads the single canonical catalog index. Explicit deep search
validates the registered narrative, cast, quest, scene, visual, audio and QA
source for each filtered project; malformed or linked input fails closed, and
results always carry non-certification status. Search is authoring discovery,
not proof that a matching game/asset has been compiled or qualified. Query
and result bounds prevent accidental log flooding; no artificial cap on
catalog growth is introduced.
