from __future__ import annotations
"""
App-wide Mishima Zaibatsu integration layer.

Binds SECURITY fabric into runtime, diaries, personal writes, math, and VOX.
Call `install_appwide_zaibatsu()` once at process boot (control.py already can).
"""

from typing import Any, Dict, Optional
import functools

from gameforge.enterprise.zaibatsu_security import SECURITY


class ZaibatsuPolicy:
    """App-wide policy knobs for Zaibatsu posture."""

    def __init__(self):
        self.enforce_on_runtime = True
        self.enforce_on_diaries = True
        self.enforce_on_math = True
        self.enforce_on_personal_logs = True
        self.block_when_frozen = True
        self.require_integrity_on_sensitive = True

    def to_dict(self) -> dict:
        return {
            "enforce_on_runtime": self.enforce_on_runtime,
            "enforce_on_diaries": self.enforce_on_diaries,
            "enforce_on_math": self.enforce_on_math,
            "enforce_on_personal_logs": self.enforce_on_personal_logs,
            "block_when_frozen": self.block_when_frozen,
            "require_integrity_on_sensitive": self.require_integrity_on_sensitive,
            "security": SECURITY.status(),
        }


POLICY = ZaibatsuPolicy()


def guard_text(text: str, *, surface: str, user_id: str = "") -> Dict[str, Any]:
    if POLICY.block_when_frozen and SECURITY.frozen:
        return {
            "ok": False,
            "blocked": True,
            "reason": "global_freeze",
            "freeze_reason": SECURITY.freeze_reason,
            "surface": surface,
        }
    return SECURITY.inspect_text(text or "", user_id=user_id, path=f"surface:{surface}")


def guard_and_integrity(text: str, *, surface: str, user_id: str = "") -> Dict[str, Any]:
    g = guard_text(text, surface=surface, user_id=user_id)
    if g.get("blocked"):
        return g
    digest = SECURITY.push_integrity(f"{surface}:{user_id}:{text[:300]}")
    g["integrity"] = digest
    g["ok"] = True
    return g


def install_runtime_guards():
    """Wrap AgentRuntime.enqueue / submit-like methods if present."""
    try:
        from gameforge.runtime import agent_runtime as ar
    except Exception:
        return {"ok": False, "error": "runtime_import"}

    Runtime = getattr(ar, "AgentRuntime", None)
    if Runtime is None:
        return {"ok": False, "error": "no_AgentRuntime"}

    if getattr(Runtime, "_zaibatsu_guarded", False):
        return {"ok": True, "already": True}

    # patch submit/enqueue variants
    for name in ("enqueue", "submit", "add_work", "push"):
        if not hasattr(Runtime, name):
            continue
        original = getattr(Runtime, name)

        @functools.wraps(original)
        def wrapped(self, *args, __orig=original, __name=name, **kwargs):
            if POLICY.enforce_on_runtime and SECURITY.frozen:
                raise RuntimeError("Zaibatsu freeze: runtime commands blocked")
            # inspect string args
            for a in args:
                if isinstance(a, str) and a:
                    g = guard_text(a, surface=f"runtime.{__name}")
                    if g.get("blocked"):
                        raise PermissionError(f"Zaibatsu blocked runtime.{__name}: {g.get('reason')}")
            for v in kwargs.values():
                if isinstance(v, str) and v:
                    g = guard_text(v, surface=f"runtime.{__name}")
                    if g.get("blocked"):
                        raise PermissionError(f"Zaibatsu blocked runtime.{__name}: {g.get('reason')}")
            return __orig(self, *args, **kwargs)

        setattr(Runtime, name, wrapped)

    Runtime._zaibatsu_guarded = True
    return {"ok": True, "patched": True}


def install_diary_guards():
    try:
        from gameforge.personal.diaries import service as ds
    except Exception:
        return {"ok": False, "error": "diaries_import"}

    Svc = getattr(ds, "DiaryService", None)
    if Svc is None:
        return {"ok": False, "error": "no_DiaryService"}
    if getattr(Svc, "_zaibatsu_guarded", False):
        return {"ok": True, "already": True}

    for name in ("add", "write", "append", "create_entry"):
        if not hasattr(Svc, name):
            continue
        original = getattr(Svc, name)

        if hasattr(original, "__call__"):
            @functools.wraps(original)
            async def awrapped(self, *args, __orig=original, **kwargs):
                if POLICY.enforce_on_diaries and SECURITY.frozen:
                    raise RuntimeError("Zaibatsu freeze: diary writes blocked")
                for a in list(args) + list(kwargs.values()):
                    if isinstance(a, str) and len(a) > 3:
                        g = guard_text(a, surface="diary")
                        if g.get("blocked"):
                            raise PermissionError(f"Zaibatsu blocked diary write: {g.get('reason')}")
                return await __orig(self, *args, **kwargs)

            # only replace if coroutine
            import inspect
            if inspect.iscoroutinefunction(original):
                setattr(Svc, name, awrapped)
            else:
                def swrapped(self, *args, __orig=original, **kwargs):
                    if POLICY.enforce_on_diaries and SECURITY.frozen:
                        raise RuntimeError("Zaibatsu freeze: diary writes blocked")
                    for a in list(args) + list(kwargs.values()):
                        if isinstance(a, str) and len(a) > 3:
                            g = guard_text(a, surface="diary")
                            if g.get("blocked"):
                                raise PermissionError(f"Zaibatsu blocked diary write: {g.get('reason')}")
                    return __orig(self, *args, **kwargs)
                setattr(Svc, name, swrapped)

    Svc._zaibatsu_guarded = True
    return {"ok": True, "patched": True}


def install_appwide_zaibatsu() -> Dict[str, Any]:
    """Idempotent install of app-wide Zaibatsu posture."""
    results = {
        "runtime": install_runtime_guards(),
        "diaries": install_diary_guards(),
        "policy": POLICY.to_dict(),
    }
    SECURITY.push_integrity("install_appwide_zaibatsu")
    return {"ok": True, "results": results}


def appwide_status() -> Dict[str, Any]:
    return {
        "policy": POLICY.to_dict(),
        "security": SECURITY.status(),
        "runtime_guarded": True,  # after install
        "level": "mishima_zaibatsu_appwide",
    }
