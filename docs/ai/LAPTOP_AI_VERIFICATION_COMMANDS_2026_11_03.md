# Exact commands: source contracts vs actual model E2E

The repository-wide source commands below are read-only except Python bytecode
cache writes by `compileall`; none creates a model or substitutes for an
independently approved artifact.

```bash
python scripts/check_ai_laptop_runtime.py
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.cli
python -m unittest discover -s skeleton/testing -p 'test_laptop_*.py' -q
```

For a real approved install and actual model generation:

```bash
python scripts/run_ai_laptop_native_e2e.py \
  --model-root /private/installed-gguf \
  --state-dir /private/state \
  --capacity-root /private/capacity \
  --tenant local --subject operator \
  --prompt-stdin --approve-real-model-test < /private/prompt.txt
```

The real acceptance command intentionally refuses to run without both an
operator-approved flag and an installed local GGUF source. It executes a
native turn, compares the authoritative replay receipt, releases the model
and reopens the database in read-only diagnostic mode. This is evidence for
that exact checkpoint, runtime configuration and machine only.

The source test suite uses a clearly labeled contract-only test double for
API framing and input/refusal checks; it **does not** pretend that it ran a
native model. Any pending CI, skipped device test, failed antivirus gate,
uncertified weights or unreviewed model license remains a release hold.
