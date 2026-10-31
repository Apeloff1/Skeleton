"""
Queue-12 pin for local AI. RMSNorm + SiLU in attn, LoRA bank, beam, accum, gossip.
Add missing tests only. Do not re-derive.
"""
KERNELS = ["rmsnorm", "silu", "lora_bank", "beam", "accum", "gossip"]

def pin_kernels() -> list:
    return KERNELS
