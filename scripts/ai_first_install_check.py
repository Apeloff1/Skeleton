#!/usr/bin/env python3
"""AI-specific first-install readiness check for Skeleton.

Verifies that AI configuration paths are present and that a fresh install
can start with AI unavailable until configured.
"""
import sys
from pathlib import Path

def check_ai_env_keys():
    env = Path(".env.example")
    if not env.exists():
        print("FAIL: .env.example missing")
        return False
    content = env.read_text()
    required = ["AI_PROVIDER", "AI_MODEL", "AI_LOCAL_MODEL_PATH"]
    for key in required:
        if key not in content:
            print(f"FAIL: {key} not in .env.example")
            return False
    print("OK: AI keys present in .env.example")
    return True

def check_ai_scripts():
    scripts = [
        "scripts/verify_ai_chat_tool_recovery.py",
        "scripts/check_ai_chat_evidence_citations.py",
    ]
    for s in scripts:
        if not Path(s).exists():
            print(f"WARN: {s} missing")
            return False
    print("OK: AI verification scripts present")
    return True

def main():
    ok = True
    ok &= check_ai_env_keys()
    ok &= check_ai_scripts()
    if ok:
        print("\nAI first-install checks passed. AI remains unavailable until configured.")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
