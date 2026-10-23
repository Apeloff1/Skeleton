"""skeleton/gates/import_1000x.py
1000x extreme complete import gates.
Full fail-closed.
Fail-closed.
"""
class GateError(Exception):
    pass

class ImportGate1000x:
    def check(self, stored_prose: int = 0) -> bool:
        if stored_prose != 0:
            raise GateError("fail-closed 1000")
        return True
