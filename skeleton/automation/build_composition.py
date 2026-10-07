"""Bind multiple accepted task artifacts into one deterministic build identity."""
from __future__ import annotations
import hashlib
def composition_digest(receipts:tuple[tuple[str,str],...])->str:
 if len(receipts)!=len({x[0] for x in receipts}):raise ValueError("duplicate task receipt")
 material="\n".join(f"{a}:{b}" for a,b in sorted(receipts))
 return hashlib.sha256(material.encode()).hexdigest()
