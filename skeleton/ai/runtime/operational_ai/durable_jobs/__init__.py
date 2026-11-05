"""Offline AI work custody: bounded scheduling into the existing native service.

No hosted provider, alternate chat authority, autonomous effects or unverified
model is created here. SQLite stores sensitive prompts; use owner-private storage.
"""
from .spec import JobSpec, JobIdentity, WorkLimits
from .store import JobStore, ClaimedJob
from .bridge import NativeJobBridge
from .errors import JobDenied

__all__ = ["JobSpec","JobIdentity","WorkLimits","JobStore","ClaimedJob","NativeJobBridge","JobDenied"]
