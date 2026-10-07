# PR #3474 seam — Deterministic text-to-token pipeline

Branch: `automation/llm-token-pipeline-20261007`
Module: `skeleton/ai/pr_seams/deterministic_token_pipeline.py`
Test: `tests/test_deterministic_token_pipeline.py`

## Compile

```bash
python -m unittest tests.test_deterministic_token_pipeline
```

The organ is pure. No torch. No network. No Hugging Face import.
Exit cards set `stored_prose=0` and cite this pull request.
Do not merge from this seam. The branch stays open until the operator lands it.

## Contract

- kind: `token-pipeline`
- law: stored_prose=0
- citation: https://github.com/Apeloff1/Skeleton/pull/3474
- parent cite: #80
