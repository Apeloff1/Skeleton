# Skeleton Beta Tester Guide — November 2026

Welcome, beta tester. This is the full operational prototype.

## Install
```bash
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton
git checkout draft-hyper-nov2026
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m api.main
```

## What to test
1. Jeeves chat: POST /jeeves/start then /jeeves/respond
2. GameForge emit: POST /forge/emit with a brief
3. Godot pack: check emitted world.tscn loads in Godot 4
4. Cockpit critique after a run
5. Economy cards and chronicle helix

## Expected
- No stubs
- Fail-closed errors
- Complete responses
- Beta-ready quality

Report issues with vertical + finding.
