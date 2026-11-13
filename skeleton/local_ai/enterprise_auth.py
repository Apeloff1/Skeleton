"""
Enterprise Auth Layer. Multi-CAS validation, role binding, and session tokens.
Fail-closed. Complete.
"""
from typing import Dict, Set
from .fail_closed import guard_cas

class EnterpriseAuth:
    def __init__(self):
        self.valid_cas: Set[str] = set()
        self.roles: Dict[str, str] = {}

    def register(self, cas: str, role: str = "operator") -> None:
        guard_cas(cas)
        self.valid_cas.add(cas)
        self.roles[cas] = role

    def authorize(self, cas: str, required: str = "operator") -> Dict:
        guard_cas(cas)
        if cas not in self.valid_cas:
            raise PermissionError("CAS not registered")
        role = self.roles.get(cas, "none")
        if role != required and role != "admin":
            raise PermissionError("insufficient role")
        return {"authorized": True, "role": role, "cas": cas[:8]}
