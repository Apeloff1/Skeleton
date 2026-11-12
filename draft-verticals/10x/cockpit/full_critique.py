"""Full 4-axis critique cockpit with Monte Carlo, cut sets era, balance cards.
Max capability Nov 2026.
"""
from typing import Dict, List
import random
import statistics

class FullCritique:
    AXES = ["fun", "clarity", "feasibility", "originality", "accessibility", "performance", "security", "scalability"]

    def run_monte_carlo(self, n: int = 5000) -> Dict:
        scores = {a: [max(0, min(1, random.gauss(0.75, 0.12))) for _ in range(n)] for a in self.AXES}
        summary = {a: {"mean": statistics.mean(scores[a]), "stdev": statistics.stdev(scores[a])} for a in self.AXES}
        weakest = min(summary, key=lambda k: summary[k]["mean"])
        return {"summary": summary, "weakest": weakest, "cut_era": True, "recommendation": f"Reinforce {weakest} for completionist max output"}

    def balance_card(self, critique: Dict) -> Dict:
        return {"card": "balance", "weakest": critique["weakest"], "scores": {k: v["mean"] for k,v in critique["summary"].items()}}
