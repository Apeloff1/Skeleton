"""
Registry of adapter capability cards. Every Wave 3 layer exports capabilities with owner contract failure_modes obs security.
"""
CARDS = []

def export(name: str, owner: str) -> None:
    CARDS.append({"name": name, "owner": owner})
