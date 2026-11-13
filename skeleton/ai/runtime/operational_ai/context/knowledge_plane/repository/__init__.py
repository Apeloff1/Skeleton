"""Exact-Git-object AI source acquisition for the private knowledge plane."""
from .service import index_repository
from .git_objects import GitSource
from .contracts import GitIndexItem,GitSourceError
__all__=['index_repository','GitSource','GitIndexItem','GitSourceError']
