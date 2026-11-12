# Longform Beta Tester Guide — Skeleton Complete Vision

## Status
All verticals complete. Adversarial review passed. Beta ready.

## Install
```bash
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton
git checkout draft-hyper-nov2026
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic
python -m longform.api.complete_beta
```

## Endpoints
- POST /jeeves/start
- POST /jeeves/respond
- POST /forge/execute
- GET /beta/status

## Expected
Complete responses. No stubs. Fail-closed. End-user expectations met.
