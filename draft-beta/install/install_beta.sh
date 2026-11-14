#!/bin/bash
set -e
echo "Installing Skeleton Beta Prototype..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "Ready. Run: python -m api.main"
