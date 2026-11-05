"""Time-dependent source expiry with explicit UTC comparison."""
from __future__ import annotations
from datetime import datetime,timezone
from .contracts import ContextError


def current_source(valid_until:str|None,now:datetime)->bool:
    if not isinstance(now,datetime) or now.tzinfo is None:raise ContextError('timezone-aware clock required')
    if valid_until is None:return True
    try:date=datetime.fromisoformat(valid_until.replace('Z','+00:00'))
    except ValueError as exc:raise ContextError('invalid source expiry') from exc
    if date.tzinfo is None:raise ContextError('source expiry must have UTC offset')
    return now.astimezone(timezone.utc)<=date.astimezone(timezone.utc)
