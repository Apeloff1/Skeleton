# Local game Pareto training (candidate only)

This operator fine-tunes the **existing Skeleton NumPy recurrent language model** on
an original game-design curriculum. It is an inexpensive learning experiment,
**not** training for the Jeeves production LLM, the game's action-policy learner,
a GGUF model, or the native transformer. It does not crawl, call a provider,
alter an existing checkpoint, or automatically promote a candidate.

## What Pareto means here

The schedule focuses 80% of training exposures on 20% of the *distinct*
authored examples. The top case in each family is chosen using:

    priority = (impact * reusability) / (1 + effort + risk)

Scores are authored heuristics, not empirical measurements or a computed
Pareto frontier. Four tail examples in each family still receive exposure.
This prevents the scheduler from entirely dropping specialized cases.

| Competency family | Training cases | Held-out cases | Exposure share |
| --- | ---: | ---: | ---: |
| Game mechanics | 5 | 2 | 20% |
| Narrative / canon | 5 | 2 | 20% |
| NPC memory / simulation | 5 | 2 | 15% |
| World exploration | 5 | 2 | 15% |
| Progression / economy | 5 | 2 | 10% |
| Editors / engineering | 5 | 2 | 10% |
| Accessibility / tutorials | 5 | 2 | 5% |
| Review / originality | 5 | 2 | 5% |
| **Total** | **40** | **16** | **100%** |

One full training epoch schedules 160 examples: 128 core exposures and 32
tail exposures. Held-out examples are never inserted into the schedule. All
examples are newly authored generic text; copyrighted game dialogue, ROMs,
proprietary code and unverified web sources are absent.

## Inspect without training

From the repository checkout:

    python -m skeleton.ai.runtime.inference.game_pareto_train --plan

With the package installed, the equivalent console command is:

    skeleton-game-pareto-train --plan

The JSON output includes the curriculum version and digests of the curriculum,
deterministic exposure schedule, and held-out examples. It is valid even when
no model checkpoint is available.

## Fine-tune an existing local model

You must already have a **Skeleton NumPy recurrent LM artifact JSON** created by
the local-model training path. This is not a GGUF, transformer checkpoint, or
game-policy file:

    python -m skeleton.ai.runtime.inference.game_pareto_train \
      --base-artifact ./local-recurrent-model.json \
      --output ./game-pareto-candidate.json \
      --epochs 1 \
      --learning-rate 0.005

The parent checkpoint and the output must be different files. Output must
not exist already. Use a new filename for each candidate.

Optionally supply an independent general-domain retention corpus so that
game-domain specialization does not silently destroy an observed capability:

    python -m skeleton.ai.runtime.inference.game_pareto_train \
      --base-artifact ./local-recurrent-model.json \
      --output ./game-pareto-with-retention.json \
      --retention-corpus ./general-eval.txt

Retention documents are **evaluation only**, never included in weight
updates, and capped at 256 KiB combined. They must be original or appropriately
licensed, and must be held out from all training.

## Explicit scratch demonstration

If no existing local recurrent artifact is available, **only** an explicit
bootstrap flag permits training a newly initialized RNN. This is not a
fine-tune of the user's existing model, nor the Jeeves LLM:

    python -m skeleton.ai.runtime.inference.game_pareto_train \
      --bootstrap --model-id pareto-demo --hidden-size 32 \
      --output ./pareto-demo-candidate.json

This is a minimal educational checkpoint; it cannot be expected to generate
coherent long-form game designs. A rejection may produce no output artifact.

## Export chat fine-tuning datasets

For transformer/LLM training frameworks, the original curriculum can also be
exported as standard chat-message JSONL rather than being trained directly by
the NumPy RNN operator:

    python -m skeleton.ai.runtime.inference.game_pareto_dataset \
      --output ./game-pareto-train.jsonl

Or, with the package installed:

    skeleton-game-pareto-export --output ./game-pareto-train.jsonl

This writes **three new files** without overwriting any existing file:
training JSONL (160 records, including repeated core cases), held-out
evaluation JSONL (16 separate cases), and a manifest JSON with SHA-256 hashes,
category budgets, and dataset provenance. A manifest is created last, after
the two data files. Do **not** include the held-out file in training. All
texts are authored in-repository, not scraped game IP.

These records can be adapted to a compatible LoRA/SFT pipeline by a separate
operator, with a **model-specific tokenizer, optimizer, checkpoint, and actual
training execution**. Exporting the dataset performs none of those actions.
There is no claim that the existing Jeeves LLM has been updated by export.

## Admission and interpretation

Every run records training loss, held-out aggregate and per-domain loss,
parent/candidate model digests, curriculum/schedule digests and a deterministic
training receipt. Only a candidate with improving held-out aggregate loss,
no per-domain regression beyond the configured 10% default, no optional
retention regression beyond 5%, and changed parameters is accepted.

A rejected candidate is **not** written to its output path. The JSON status
and rejection reasons are printed to stdout. The CLI uses exit code 3 for a
measured evaluation rejection, 2 for invalid arguments/inputs, and 0 for an
accepted candidate or a curriculum inspection.

These are **byte-token prediction-loss** measurements, not gameplay quality,
reasoning, authored-story quality, adversarial assurance, or general-capability
proof. Even an accepted candidate is not promoted and cannot be presented as
production-ready. Before any higher-stakes promotion, independently compare
the candidate to its parent on fresh gameplay tasks, canon challenges,
reasoning evaluations, originality checks, and device performance. Production
promotion stays in the application's existing governed assurance plane.

The operator does not add, trigger or modify GitHub Actions workflows.

## Focused local contract checks

    python -m unittest skeleton.testing.test_game_pareto_train

No full-repository test pass is implied by this small focused check.
