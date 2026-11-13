"""Finite async adapter around the existing authoritative OfflineAIService."""
from .executor import AsyncAIExecutor,JobReceipt
from .recovery import diagnose_incomplete
__all__=['AsyncAIExecutor','JobReceipt','diagnose_incomplete']
