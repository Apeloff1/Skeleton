"""
Health check for local AI boilerplate. Verifies seams, adapter, and bridge load.
"""
from . import get_complete
from .version import __version__, __seams__

def health() -> dict:
    ai = get_complete()
    status = ai.status()
    return {
        "version": __version__,
        "declared_seams": __seams__,
        "loaded_seams": status["seams"],
        "adapter": status["adapter"],
        "bridge": status["bridge"],
        "healthy": status["seams"] >= __seams__ and status["status"] == "complete"
    }
