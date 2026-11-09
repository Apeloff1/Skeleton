"""Local OS idle signals for Dragon's consent-bound host, not a web API.

This adapter supplies real local keyboard/mouse idle observations where
supported. The authenticated host MUST additionally supply a trusted check
for session unlocked, competing foreground work, Dragon consent, and available
resource/network budgets. An unknown OS, Wayland compositor, remote session,
failed library call, or invalid reading fails closed rather than assuming idle.

The probe only reads activity duration. No key events, typed text, user-window
titles, screenshots, web requests, threads, or background timers are stored.
Call probe.observe from the existing authorized native app event loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable
import ctypes
import ctypes.util
import os
import sys
import time

from .dragon_family import IdleWindow, _epoch


class NativeIdleUnavailable(PermissionError):
    """No reliable local OS idle observation is available; deny research."""


def _windows_idle_seconds() -> float:
    if sys.platform != "win32":
        raise NativeIdleUnavailable("Windows native idle API unavailable")
    try:
        from ctypes import wintypes

        class LastInputInfo(ctypes.Structure):
            _fields_ = [("cbSize",wintypes.UINT),("dwTime",wintypes.DWORD)]

        info=LastInputInfo()
        info.cbSize=ctypes.sizeof(LastInputInfo)
        u32=ctypes.WinDLL("user32",use_last_error=True)
        k32=ctypes.WinDLL("kernel32",use_last_error=True)
        u32.GetLastInputInfo.argtypes=[ctypes.POINTER(LastInputInfo)]
        u32.GetLastInputInfo.restype=wintypes.BOOL
        k32.GetTickCount64.argtypes=[]
        k32.GetTickCount64.restype=ctypes.c_ulonglong
        if not u32.GetLastInputInfo(ctypes.byref(info)):
            raise NativeIdleUnavailable("Windows last input query refused")
        now=int(k32.GetTickCount64())
        # GetLastInputInfo is a 32-bit tick, so compare modulo 2^32.
        # The 24h admission ceiling below also avoids treating stale wraps
        # as infinitely old, trustworthy input evidence.
        elapsed=((now & 0xffffffff)-int(info.dwTime)) & 0xffffffff
        return elapsed/1000.0
    except (AttributeError, OSError, ValueError) as exc:
        raise NativeIdleUnavailable("Windows input idle observer unavailable") from exc


def _macos_idle_seconds() -> float:
    if sys.platform != "darwin":
        raise NativeIdleUnavailable("macOS native idle API unavailable")
    try:
        lib=ctypes.util.find_library("ApplicationServices")
        if not lib:
            raise NativeIdleUnavailable("macOS Quartz idle API unavailable")
        quartz=ctypes.CDLL(lib)
        seconds=quartz.CGEventSourceSecondsSinceLastEventType
        seconds.argtypes=[ctypes.c_uint32,ctypes.c_uint32]
        seconds.restype=ctypes.c_double
        # 0 = combined system session, 0xffffffff = any input event.
        return float(seconds(0,0xffffffff))
    except (AttributeError, OSError, ValueError) as exc:
        raise NativeIdleUnavailable("macOS input idle observer unavailable") from exc


def _linux_x11_idle_seconds() -> float:
    if not sys.platform.startswith("linux"):
        raise NativeIdleUnavailable("Linux X11 idle API unavailable")
    # XWayland may report only X11 application input, missing Wayland
    # compositor activity. Never trust it as a full-device idle signal.
    if os.environ.get("WAYLAND_DISPLAY"):
        raise NativeIdleUnavailable("Wayland requires a trusted compositor idle provider")
    display_name=os.environ.get("DISPLAY","")
    if not display_name:
        raise NativeIdleUnavailable("graphical X11 display is unavailable")
    # Remote/forwarded X11 servers are not authoritative sensors for the
    # current user's local keyboard. Only accept a local Unix display.
    if not (display_name.startswith(":") or display_name.startswith("unix:")):
        raise NativeIdleUnavailable("remote X11 display cannot attest local user input")
    display=None
    try:
        libx=ctypes.CDLL("libX11.so.6")
        libss=ctypes.CDLL("libXss.so.1")

        class XScreenSaverInfo(ctypes.Structure):
            _fields_=[("window",ctypes.c_ulong),
                      ("state",ctypes.c_int),
                      ("kind",ctypes.c_int),
                      ("til_or_since",ctypes.c_ulong),
                      ("idle",ctypes.c_ulong),
                      ("event_mask",ctypes.c_ulong)]

        libx.XOpenDisplay.argtypes=[ctypes.c_char_p]
        libx.XOpenDisplay.restype=ctypes.c_void_p
        libx.XDefaultRootWindow.argtypes=[ctypes.c_void_p]
        libx.XDefaultRootWindow.restype=ctypes.c_ulong
        libx.XCloseDisplay.argtypes=[ctypes.c_void_p]
        libx.XCloseDisplay.restype=ctypes.c_int
        libss.XScreenSaverAllocInfo.argtypes=[]
        libss.XScreenSaverAllocInfo.restype=ctypes.POINTER(XScreenSaverInfo)
        libss.XScreenSaverQueryInfo.argtypes=[
            ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(XScreenSaverInfo)]
        libss.XScreenSaverQueryInfo.restype=ctypes.c_int
        libx.XFree.argtypes=[ctypes.c_void_p]
        libx.XFree.restype=ctypes.c_int
        display=libx.XOpenDisplay(None)
        if not display:
            raise NativeIdleUnavailable("cannot open local X11 display")
        root=libx.XDefaultRootWindow(display)
        info=libss.XScreenSaverAllocInfo()
        if not bool(info):
            raise NativeIdleUnavailable("X11 idle context unavailable")
        try:
            ok=libss.XScreenSaverQueryInfo(display,root,info)
            if ok!=1:
                raise NativeIdleUnavailable("X11 idle query refused")
            return float(info.contents.idle)/1000.0
        finally:
            libx.XFree(ctypes.cast(info,ctypes.c_void_p))
    except (AttributeError, OSError, ValueError) as exc:
        raise NativeIdleUnavailable("X11 input idle observer unavailable") from exc
    finally:
        if display:
            libx.XCloseDisplay(display)


def os_input_idle_seconds() -> float:
    """No fallback to a fabricated idle duration on unsupported systems."""
    if sys.platform=="win32":
        return _windows_idle_seconds()
    if sys.platform=="darwin":
        return _macos_idle_seconds()
    if sys.platform.startswith("linux"):
        return _linux_x11_idle_seconds()
    raise NativeIdleUnavailable("native input idle observation unavailable")


@dataclass(frozen=True)
class NativeHostSignals:
    """Separately trusted host observations, never a browser request payload."""
    session_unlocked: bool
    user_foreground_active: bool
    running_foreground_jobs: int
    resources_available: bool
    research_consent_active: bool

    def validate(self) -> None:
        if not all(type(v) is bool for v in (
                self.session_unlocked,self.user_foreground_active,
                self.resources_available,self.research_consent_active)):
            raise NativeIdleUnavailable("invalid native host activity signals")
        if (type(self.running_foreground_jobs) is not int or
                not 0<=self.running_foreground_jobs<=1000000):
            raise NativeIdleUnavailable("unknown foreground job occupancy")


class NativeDragonIdleProbe:
    """Owner-side native adapter for DragonIdleHostControl.tick.

    The application passes os_input_idle_seconds by default. Runtime model
    code never creates this probe from a remote HTTP request. All gates are
    refreshed on each observe() invocation, including after captures.
    """
    def __init__(
        self, *,
        host_signals: Callable[[], NativeHostSignals],
        input_idle_seconds: Callable[[], float] = os_input_idle_seconds,
        clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        maximum_sample_duration: float = 2.0,
        maximum_trusted_idle_seconds: float = 86400.0,
    ):
        if not all(callable(fn) for fn in (
                host_signals,input_idle_seconds,clock,monotonic_clock)):
            raise ValueError("native host observer callbacks must be callable")
        if (type(maximum_sample_duration) not in (int,float) or
                not isfinite(maximum_sample_duration) or
                not 0.01<=maximum_sample_duration<=10):
            raise ValueError("invalid native observation deadline")
        if (type(maximum_trusted_idle_seconds) not in (int,float) or
                not isfinite(maximum_trusted_idle_seconds) or
                not 300<=maximum_trusted_idle_seconds<=86400):
            raise ValueError("invalid native input freshness bound")
        self.host_signals=host_signals
        self.input_idle_seconds=input_idle_seconds
        self.clock=clock
        self.monotonic_clock=monotonic_clock
        self.maximum_sample_duration=float(maximum_sample_duration)
        self.maximum_trusted_idle_seconds=float(maximum_trusted_idle_seconds)

    def observe(self) -> IdleWindow:
        try:
            start=self.monotonic_clock()
            now=_epoch(self.clock())
            elapsed=self.input_idle_seconds()
            signals=self.host_signals()
            end=self.monotonic_clock()
            if (type(start) not in (int,float) or
                    type(end) not in (int,float) or
                    not isfinite(start) or not isfinite(end) or
                    end<start or end-start>self.maximum_sample_duration):
                raise NativeIdleUnavailable("native activity observation is stale")
            if (type(elapsed) not in (int,float) or not isfinite(elapsed) or
                    not 0<=elapsed<=self.maximum_trusted_idle_seconds or
                    elapsed>now):
                raise NativeIdleUnavailable("invalid local input-idle measurement")
            if not isinstance(signals,NativeHostSignals):
                raise NativeIdleUnavailable("authenticated native host status unavailable")
            signals.validate()
            # A locked, remote or incomplete desktop session must not report
            # idle availability. This is fail-closed even if the OS duration
            # claims the keyboard has been untouched for hours.
            if not signals.session_unlocked:
                raise NativeIdleUnavailable("desktop session not confirmed unlocked")
            return IdleWindow(
                now=now,last_user_activity_at=now-float(elapsed),
                busy_jobs=signals.running_foreground_jobs,
                foreground_active=signals.user_foreground_active,
                consent=signals.research_consent_active,
                resources_available=signals.resources_available,
            )
        except NativeIdleUnavailable:
            raise
        except (ValueError,TypeError,OSError,RuntimeError,OverflowError) as exc:
            raise NativeIdleUnavailable("native host observation denied") from exc
