# Weather delivery route planner — deterministic proof

`python -m skeleton weather-deliveries-plan demo` searches the original
Lantern Hollow caravan delivery game for the shortest legal complete route.
It enumerates only canonical collect, travel and wait actions. Weather gates,
inventory, authored deadlines and delivery dependencies are enforced by the
same replay-verified runtime used by interactive play.

```sh
python -m skeleton weather-deliveries-plan demo
python -m skeleton weather-deliveries-plan solve --source-json '<source>' --max-states 128 --max-depth 16
python -m skeleton weather-deliveries-plan solve --session-json '<checkpoint>'
python -m skeleton weather-deliveries-plan verify --report-json '<report>'
```

A solved report contains a source-bound starting checkpoint, canonical action
witness, and verified portable terminal package. A terminal checkpoint can
produce a zero-action witness. Bounded exhaustion is **inconclusive**, never
an invented impossibility proof. `verify` re-runs the bounded search and
checks the complete report and all nested canonical save/replay contracts.
Search is deterministic, offline, and limited to 256 states and depth 32.
No provider, device, or consumer release qualification is asserted.
