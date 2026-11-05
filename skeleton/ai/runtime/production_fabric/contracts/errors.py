"""Typed failures; never convert a denied operation into a best-effort success."""

class FabricError(ValueError):
    code = 'fabric-invalid'

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class ContractError(FabricError):
    code = 'contract-invalid'

class AuthorizationError(FabricError):
    code = 'authority-denied'

class ConflictError(FabricError):
    code = 'transaction-conflict'

class IntegrityError(FabricError):
    code = 'integrity-failure'

class BudgetError(FabricError):
    code = 'budget-exhausted'

class UnavailableError(FabricError):
    code = 'capability-unavailable'
