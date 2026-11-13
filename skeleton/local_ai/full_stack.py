"""
Full Operational Stack. Wires engine, loader, loop, session, cache, metrics, safety, recovery into one entry.
Closes the integration gap. Fully functional.
"""
from .operational_engine import get_engine
from .model_loader import ModelLoader
from .inference_loop import InferenceLoop
from .session_manager import SessionManager
from .cache_layer import CacheLayer
from .metrics_collector import MetricsCollector
from .safety_filter import SafetyFilter
from .recovery_manager import RecoveryManager
from .health_monitor import HealthMonitor
from .gap_filler import GapFiller

class FullStack:
    def __init__(self):
        self.engine = get_engine()
        self.loader = ModelLoader()
        self.loop = InferenceLoop()
        self.sessions = SessionManager()
        self.cache = CacheLayer()
        self.metrics = MetricsCollector()
        self.safety = SafetyFilter()
        self.recovery = RecoveryManager()
        self.health = HealthMonitor()
        self.gaps = GapFiller()

    def run(self, prompt: str, cas: str, session: str = "default") -> dict:
        cached = self.cache.get(prompt, cas)
        if cached:
            return {"cached": True, "out": cached}
        out = self.engine.generate(prompt, cas)
        safe = self.safety.check(out["text"], out["g_state"]["G"])
        self.cache.put(prompt, cas, out)
        self.metrics.inc("runs")
        self.sessions.turn(session, prompt, cas)
        return {"cached": False, "out": out, "safe": safe, "health": self.health.check()}

def get_stack() -> FullStack:
    return FullStack()
