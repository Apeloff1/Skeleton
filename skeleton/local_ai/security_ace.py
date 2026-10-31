"""
ACE fail-close for local AI. Align with PR 87. Secret scan. No live secrets.
"""
FORBIDDEN = [".env", "token", "pem", "secret"]

def scan(path: str) -> bool:
    return not any(f in path.lower() for f in FORBIDDEN)
