"""Native inference is only available through the guarded provider runtime.

The legacy local_ai operational engine synthesizes placeholder text and cannot
satisfy a real model inference request. Refuse rather than present it as GGUF.
"""
from typing import Iterator, Dict

class InferenceLoop:
    def run(self, prompt: str, cas: str, steps: int = 8) -> Iterator[Dict]:
        from .fail_closed import guard_cas
        guard_cas(cas)
        raise RuntimeError("LOCAL_GGUF_NOT_ACTIVATED: use guarded skeleton.provider_runtime")
        yield {}  # preserve generator interface; unreachable

    def complete(self, prompt: str, cas: str) -> Dict:
        return {"final": next(self.run(prompt, cas)), "operational": False}
