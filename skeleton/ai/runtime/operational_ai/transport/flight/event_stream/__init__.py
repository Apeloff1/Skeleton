"""Private, bounded, resumable observation of authoritative flight transitions."""
from .cursor import CursorAuthority, StreamCursor
from .reader import EventReader, StreamSnapshot
from .service import EventStream
__all__ = ["CursorAuthority", "StreamCursor", "EventReader", "StreamSnapshot", "EventStream"]
