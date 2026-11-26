#!/usr/bin/env python3
"""AI response quality first-install check for Skeleton.

Verifies that AI response verification scripts are present and that
response quality gates are available for a fresh install.
"""
import sys
from pathlib import Path

def check_response_scripts():
    scripts = [
        "scripts/verify_ai_chat_tool_recovery.py",
        "scripts/check_ai_chat_evidence_citations.py",
        "scripts/verify_ai_chat_model_routing.py",
    ]
    for s in scripts:
        if not Path(s).exists():
            print(f"FAIL: {s} missing")
            return False
    print("OK: AI response quality scripts present")
    return True

def check_ai_docs():
    docs = [
        "docs/JEEVES_AI_STATIC_INTELLIGENCE_MILESTONES.md",
    ]
    for d in docs:
        if not Path(d).exists():
            print(f"WARN: {d} missing")
            return False
    print("OK: AI docs present")
    return True

def main():
    ok = True
    ok &= check_response_scripts()
    ok &= check_ai_docs()
    if ok:
        print("\nAI response quality checks passed.")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
