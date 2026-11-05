"""#807 batch B075: visual regression suite (lane quality, wave 2; depends on B071)."""
from .visual import Capture, CaptureError, VisualDiff, VisualSuite, render_scene

__all__ = ["Capture", "CaptureError", "VisualDiff", "VisualSuite", "render_scene"]
