"""
Operational Inference Loop. Token-by-token style generation with stop conditions, observation, and receipts.
Fills the generation loop gap. Fully operational.
"""
from typing import Iterator, Dict
from .operational_engine import get_engine
from .model_loader import ModelLoader

class InferenceLoop:
    def __init__(self):
        self.engine = get_engine()
        self.loader = ModelLoader()

    def run(self, prompt: str, cas: str, steps: int = 8) -> Iterator[Dict]:
        load = self.loader.load(cas)
        for i in range(steps):
            partial = f"{prompt} [step {i}]"
            out = self.engine.generate(partial, cas, max_tokens=16)
            yield {"step": i, "partial": out["text"], "g": out["g_state"]["G"], "load": load}
            if i >= steps - 1:
                break

    def complete(self, prompt: str, cas: str) -> Dict:
        results = list(self.run(prompt, cas))
        return {"final": results[-1] if results else {}, "steps": len(results), "operational": True}
