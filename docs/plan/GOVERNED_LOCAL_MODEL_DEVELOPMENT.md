# Governed local model development

The P3-T2 implementation candidate now connects observed source bytes, durable
dataset versions, actual local learning, restartable checkpoints and executable
candidate evidence. The command line entrypoint uses existing runtime owners and
does not require a hosted model or credentials.

## Build and resume a model

Provide UTF-8 files that you have permission to use. Rights references are
explicit operator declarations; the runtime binds and enforces those references
but does not independently establish ownership or consent.

```sh
python -m skeleton.ai.runtime.training.cli ./licensed-corpus.txt \
  --state-directory ./local-training-state \
  --output ./local-model.json \
  --run-id local-neural-v1 \
  --dataset-id licensed-corpus \
  --rights-ref license:owned-corpus \
  --algorithm neural --hidden-size 24 --epochs 8 \
  --max-steps 100000 --max-updates 4096
```

NumPy is required for neural training. The tested workflow uses NumPy 2.3.5.
The existing `local-inference` optional dependency group declares the project's
preferred local runtime. `--algorithm reference --order 2` selects the reference
n-gram estimator and can run without NumPy.

Run the same command after interruption. The immutable operator request, source
bytes, dataset identity, model settings, code/environment identity and budgets
must match. The trainer reloads full committed state and continues after the last
committed document. Completed retries rewrite the derived artifact from the
durable checkpoint without repeating training. A new run ID creates a new dataset
version while preserving immutable source acquisition and rights metadata.

The command prints a content-addressed receipt with dataset, quality observation,
checkpoint, model and artifact digests. Neural receipts also include observed
initial/final corpus loss and update count. It does not print corpus text.

Inputs are bounded before allocation and execution. Neural documents are at most
4096 UTF-8 bytes and the corpus at most 1 MiB. Reference documents are at most
1 MiB and the corpus at most 64 MiB. Neural steps count every UTF-8 byte target
plus EOS for every epoch; updates count complete document SGD updates. The
cumulative budget survives restart. Files must be regular, distinct and free of
symlink ancestors; input/output/database identities cannot alias.

## Inspect durable authorities

```python
from skeleton.ai.runtime.training import DatasetRegistry, TrainingRepository
from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer

datasets = DatasetRegistry("local-training-state/datasets.sqlite3")
runs = TrainingRepository("local-training-state/training.sqlite3")
try:
    model, receipt = NeuralLocalTrainer(datasets, runs).load_artifact("local-neural-v1")
    assert model.model_digest == receipt.model_digest
    sources = datasets.materialized_sources(receipt.dataset_digest)
    documents = datasets.training_corpus(receipt.dataset_digest)
finally:
    runs.close()
    datasets.close()
```

`DatasetRegistry.ingest_materialized` computes splits and quality from stored
original bytes. `MultimodalCorpus.export_text_training` supplies an immutable
manifest and exact projected documents; `DatasetRegistry.ingest_export` verifies
the declared asset/record/projection/rights/lineage bindings and exact projected
document sequence before materializing it. Original acquisition proof is
supplied by the exporter/operator. Binary media without verified text is not
silently treated as a corpus. Simulation remains an explicitly isolated purpose.

Source revocation and deletion are durable operations:

```python
datasets = DatasetRegistry("local-training-state/datasets.sqlite3")
try:
    datasets.revoke_source_rights(
        sources[0].envelope.content_digest,
        reason="Training consent withdrawn",
        command_id="withdraw-consent-001",
    )
finally:
    datasets.close()
```

`delete_source` and `delete_dataset` likewise require a reason and command ID.
Revocation, deletion, quality failure or content corruption prevents new training,
resume, completed artifact reload and CLI republication. Checkpoint and terminal
commits hold the dataset authority transaction, ordering them against independent
revocation writers. Existing derived artifacts remain separate evidence; deleting
or revoking source content does not automatically erase every prior model copy.

## Use the produced artifact

Explicit local activation uses the existing canonical provider owner:

```sh
export AI_PROVIDER=local
export AI_LOCAL_MODEL_PATH=./local-model.json
```

The optional local adapter loads and pins the artifact identity, acknowledges the
canonical construction contract, and preserves governance, resource admission,
actual usage, deadlines and cancellation. It registers no hosted fallback.
Secondary-provider and semantic-verifier configuration rejects in local mode.
The artifact is also directly reloadable through `load_local_model_artifact`.

## Measure, migrate and compensate

`EvaluationHarness` executes local model suites. `PostTrainingRunner` executes
registered deterministic environments using a bounded local policy observation,
commits episode cursors/receipts/usage together and resumes without replaying
committed callbacks. Stage metrics and qualification derive from issued executed
receipts and measured evaluation, with model/policy/curriculum identities pinned.
Policies are trusted local code declared side-effect-free; the runtime does not
sandbox arbitrary Python callbacks.

`ModelLifecycleRegistry(path="candidate-lifecycle.sqlite3")` persists MBOMs,
issued parity decisions, legal transitions, migration and rollback lineage.
`decision(digest)` reconstructs an issued handle after restart. `apply_migration`
atomically deprecates the source and activates the target in the local candidate
registry. `rollback_migration` compensates that exact transition. Independent
connections serialize and fence the same snapshot version. `backup` and
`restore_backup` validate the complete evidence graph and reject corruption or
unknown schema versions.

Candidate registry activation does not configure a production model router.
Reported parity observations and held-out declarations still require independent
provenance and production review. Distributed collectives, broad model quality,
production rollout and masterplan signoffs remain outside this candidate.

## Verification and rollback

The **AI Governed Training Pipeline** workflow checks the exact submitted head,
both executable contract validators, domain regressions, assembled restart and
engine paths, and canonical construction/provider gates. See
`machine/ai_training_pipeline.json` for the contract inventory.

To withdraw the candidate, stop new CLI and execution admission while retaining
the dataset, training, post-training and lifecycle databases and a compatible
code version. Restore lifecycle backups to a new destination only after complete
validation. Preserve full learned checkpoints and issued evidence; never recover
by inventing corpus bytes, restoring withdrawn rights, resetting usage or deleting
transition history.
