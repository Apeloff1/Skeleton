"""Fail-closed GGUF model execution in a dedicated local subprocess.

This package neither downloads a model nor starts a provider connection. The
subprocess alone holds a sealed verified GGUF image. Uncertain native results
kill the subprocess; durable requests remain explicitly recoverable, not retried.
"""
from .client import IsolatedGGUFBackend
from .contracts import IsolationPolicy, IsolationFailure, IsolationUnavailable

__all__ = ['IsolatedGGUFBackend', 'IsolationPolicy', 'IsolationFailure', 'IsolationUnavailable']
