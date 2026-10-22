"""
Operational Batch Processor. Parallel-style batch generate with shared CAS and aggregated metrics.
Fills the batch throughput gap.
"""
from typing import List, Dict
from .operational_engine import get_engine
from .metrics_collector import MetricsCollector

class BatchProcessor:
    def __init__(self):
        self.engine = get_engine()
        self.metrics = MetricsCollector()

    def process(self, prompts: List[str], cas: str) -> List[Dict]:
        results = []
        for p in prompts:
            out = self.engine.generate(p, cas)
            results.append(out)
            self.metrics.inc("batch_items")
            self.metrics.set("last_g", out["g_state"]["G"])
        return results

    def report(self) -> Dict:
        return self.metrics.snapshot()
