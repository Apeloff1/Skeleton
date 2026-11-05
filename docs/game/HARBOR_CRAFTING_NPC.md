# Lantern Quay NPC patrol and trade observations

The NPC report replays the complete authored game and records the merchant's
actual position, player position, distance, adjacency, finite stock, coins,
price and terminal state after each transition. It observes the real game
engine; it never fabricates trade access or ignores collision handling.

Commands: npc-report --bundle save.json; verify-npc-report --report report.json;
npc-forecast --bundle save.json --tick 3; verify-npc-forecast --report forecast.json.
A forecast simulates WAIT actions only and is explicitly a scenario, not a
prediction of arbitrary future player decisions. All outputs are bounded,
portable canonical JSON and reverified against original source and action
history. Correctly rehashed forged patrol or trade records are rejected.
