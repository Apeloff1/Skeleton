"""Explicit fallback for the legacy optional AI import.

The application currently imports these names for compatibility, but the active
request paths do not instantiate them. Keeping the fallback local prevents an
optional third-party integration from becoming a hard application import
requirement in CI or minimal deployments.
"""


class UserMessage:
    """Compatibility value object for legacy callers."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class LlmChat:
    """Fail-closed placeholder for the retired optional integration."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "The legacy emergentintegrations LlmChat adapter is unavailable; "
            "use the consolidated AI integration boundary instead."
        )
