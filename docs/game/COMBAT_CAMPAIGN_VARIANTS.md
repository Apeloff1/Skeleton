# Combat campaign variant comparison

`python -m skeleton combat-campaign-variants demo` compares original
source-bound authored alternatives, plays each through the canonical combat
campaign engine, and exports the selected replay-verified portable checkpoint.

The `compare` command accepts `--source-json`, `--alternatives-json`
(a list of 1–4 authoring-operation batches), and `--expected-digest`
(the exact digest of the normalized original campaign). Each batch uses
`combat-campaign-author` operations: `set-reward`, `set-turn-limit`,
or `set-foe-stat`. A stale source, duplicate candidate, invalid edit,
unearned reward, incompatible hero or invalid source fails closed.

The immutable original is always candidate zero and serves as the fallback.
The deterministic policy ranks actual terminal victory first, then remaining
hero HP, then earned currency, then original candidate order. This is a
transparent offline authoring preference, **not** a fairness guarantee or a
claim about optimal human gameplay.

The selected result is a `combat-campaign-package` bundle, with verified
source, encounter journals, save lineage, replay digest and portable manifest.
Use `combat-campaign-variants verify --report-json '<report>'` to replay
every alternative and reject a changed selection, source, reward, state or
receipt. Digests provide integrity only, not signatures or authorization.
No external content, provider, filesystem mutation or network is involved.
