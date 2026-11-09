"""Compatibility shim for the canonical deployment strategies namespace."""
from skeleton.deploy.strategies.release_notes import CATEGORIES, ChangeEntry, Release, ReleaseNotesGenerator

__all__ = ["CATEGORIES", "ChangeEntry", "Release", "ReleaseNotesGenerator"]
