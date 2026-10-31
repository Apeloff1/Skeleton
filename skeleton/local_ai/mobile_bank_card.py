"""
Mobile bank card. Speculative RAG, SSE, bench GPU, HF import stay dark on mobile.
Bank card stays green.
"""
DEFAULTS = {"speculative_rag": False, "sse": False, "bench_gpu": False, "hf_import": False, "bank_green": True}

def get_mobile_defaults() -> dict:
    return DEFAULTS.copy()
