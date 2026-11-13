"""Real offline laptop AI interface over the canonical production ExecutionSpine.

This package does not create another model engine or invent an AI answer.
"""
from .dispatcher import LaptopDispatcher
from .server import LaptopHTTPServer
from .client import LaptopClient
__all__=("LaptopDispatcher","LaptopHTTPServer","LaptopClient")
