# Game design training: checkpoint-linked quest-graph ranker (2026-10-15)

## Status and scope

This work trained a new quest-graph candidate ranking adapter, not the production Jeeves LLM. The model parent was an explicitly loaded and verified Skeleton native 32-hidden-size NumPy recurrent scratch checkpoint, obtained from the user's saved training artifacts. It remained frozen and unmodified.

The pre-existing checkpoint cannot generate coherent free-form game designs. This task trained a separate, checkpoint-bound ranking head that chooses among structured key/door quest graphs.

The runtime at skeleton/ai/game_builder/quest_graph_ranker_core.py requires explicit --checkpoint and --adapter paths. It never loads, trains, deploys, or promotes weights by default. PyTorch and NumPy are needed for ranking.

## Identical held-out requests: what changed?

Training labels came from executable graph-state checks: reachability, mandatory key/gate, no softlocks, route choices, all authored rooms reachable, pacing, edge validity and resource budget.

- Training: 1,000 generated game-design requests x 15 competing graphs = 15,000 labeled candidate designs, for 50 epochs.
- Training request seeds: 10000 through 10999.
- Standard held-out request seeds: 300000 through 300259.
  Untrained ranker: 28/260 valid. Trained ranker: 260/260 valid.
- Adversarial held-out request seeds: 800000 through 800249.
  Untrained ranker: 0/250. Earlier normally trained head: 0/250.
  Hard-negative-trained head: 250/250.
- A separate replay simulator confirmed constraints for all 510 selected graph designs.
- Unseen topology relabeling seeds 910000 through 910149: 70/150 valid raw selections. Thus the ranker does not generalize reliably to changed graph layouts.
- The runtime validates graph constraints before ranking and returns rejection when no valid candidate exists.

These are narrow procedural game-design proof obligations, not proof of compelling gameplay, creative worldbuilding, coherent dialogue, general reasoning, player enjoyment, broad game design, or production readiness. Synthetic train and evaluation cases share a narrow task schema.

## Verified checkpoint identity

Parent scratch checkpoint SHA-256:
77c6468a59bade72811952f17263807bba1c1a6f03fb302ffcbd814fd4c848b9

Parent native model digest:
c03018589425cee5188f54fc2065747cc21a032c738b340aa72a1cf1c0be8c15

New game quest ranking adapter SHA-256:
b295872edf7fd489ca39560bf1b6d849076969a81b3a484c12e70c6db96d8671

The adapter binds to both the exact parent file SHA and native model digest. Mismatched or tampered parents are rejected.

Checkpoint bytes, adapter weights, held-out evidence, independent replay, reproduction code, and failed adversarial probes are saved in the user's ChatGPT Library:
 /Skeleton-Game-Design-Training-Evidence-2026-10-15.zip

Library storage is not a GitHub repository or app deployment folder.

## Runtime operator command

Use a JSON request with a task object containing biome, goal, difficulty, min_steps, max_steps, max_edges, plus candidates as arrays of graph edges [from_node,to_node] over seven nodes: 0 start, 1 key, 2 locked gate, 3 goal, 4-6 other rooms.

    python -m skeleton.ai.game_builder.quest_graph_ranker_core \
      --checkpoint ./parent-native-checkpoint.json \
      --adapter ./quest-graph-ranker.adapter.pt \
      --request ./quest_request.json

Responses include proof checks and production_promotion: false.

## Acceptance boundary

The measured result establishes improvement only at choosing among preauthored structured quest graphs, under the tested rules. A valid candidate must already exist. The actual Jeeves production model has not been fine-tuned or promoted; that requires verified access to its real checkpoint and compatible training runtime.
