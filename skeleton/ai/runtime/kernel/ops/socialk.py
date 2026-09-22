"""Social-parsed kernel card. Hits increment on poke().

Pointers only. Houses: X / arXiv / GitHub. No post bodies.
"""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ops.flashdec import flashdec
from skeleton.kernel.ops.fp8kv import pack, unpack
from skeleton.kernel.ops.gqa import group
from skeleton.kernel.ops.linattn import linattn
from skeleton.kernel.ops.pagekv import PageKV
from skeleton.kernel.ops.sparseattn import sparse
from skeleton.kernel.ops.specdec import mtp_head, verify
from skeleton.kernel.ops.xquant import pack_x, rematerialize
from skeleton.kernel.ops.treeattn import tree
from skeleton.kernel.ops.chunkprefill import prefill
from skeleton.kernel.ops.ragged import ragged
from skeleton.kernel.ops.prefixhash import PrefixCache
from skeleton.kernel.ops.marlin import gemm4, pack4
from skeleton.kernel.ops.onlinesm import online
from skeleton.kernel.ops.packgqa import pack as pack_gqa
from skeleton.kernel.ops.persistkv import save as persist_save
from skeleton.kernel.ops.cascade import cascade
from skeleton.kernel.ops.megafuse import epilogue
from skeleton.kernel.ops.kselect import pick


CITES = (
    {"topic": "flashqla-linear", "url": "https://x.com/Alibaba_Qwen/status/2049462666734026923", "house": "X"},
    {"topic": "xquant-kv", "url": "https://arxiv.org/abs/2508.10395", "house": "arXiv"},
    {"topic": "flash-decoding", "url": "https://arxiv.org/html/2508.08192", "house": "arXiv"},
    {"topic": "flashmla", "url": "https://github.com/deepseek-ai/FlashMLA", "house": "GitHub"},
    {"topic": "paged-attention", "url": "https://arxiv.org/abs/2309.06180", "house": "arXiv"},
    {"topic": "flashprefill-v2", "url": "https://arxiv.org/abs/2608.19758", "house": "arXiv"},
    {"topic": "mpk-megakernel", "url": "https://arxiv.org/abs/2512.22219", "house": "arXiv"},
)


class SocialK:
    NAMES = (
        "linattn", "xquant", "fp8kv", "pagekv",
        "flashdec", "specdec", "mtp", "gqa", "sparseattn",
        "treeattn", "chunkprefill", "ragged", "prefixhash",
        "marlin", "onlinesm", "packgqa", "persistkv",
        "cascade", "megafuse", "kselect",
    )

    def __init__(self) -> None:
        self.hits: Dict[str, int] = {n: 0 for n in self.NAMES}

    def poke(self) -> Dict[str, Any]:
        x = [0.2, -0.1, 0.4, 0.05]
        g = [0.3, 0.0, -0.2, 0.1]
        linattn([x, g], [g, x]); self.hits["linattn"] += 1
        xq, s = pack_x(x)
        rematerialize(xq, s, [xq], s, [xq], s); self.hits["xquant"] += 1
        q, sc = pack(x)
        unpack(q, sc); self.hits["fp8kv"] += 1
        p = PageKV(page=2)
        p.put(x, g); p.put(g, x); self.hits["pagekv"] += 1
        flashdec(x, [(x, g), (g, x)]); self.hits["flashdec"] += 1
        verify([1, 2, 3], [1, 2, 9]); self.hits["specdec"] += 1
        mtp_head(x, 2); self.hits["mtp"] += 1
        group([x, g], [(x, g)]); self.hits["gqa"] += 1
        sparse(x, [(x, g), (g, x), (x, x)], keep=2); self.hits["sparseattn"] += 1
        tree(x, [(x, g)], [(g, x)]); self.hits["treeattn"] += 1
        prefill([x, g], [(x, g)], size=1); self.hits["chunkprefill"] += 1
        ragged(x, [x, g], [g, x]); self.hits["ragged"] += 1
        PrefixCache().put([1, 2], [(x, g)]); self.hits["prefixhash"] += 1
        q, s = pack4(x); gemm4(x, [q], [s]); self.hits["marlin"] += 1
        online(x, approx=True); self.hits["onlinesm"] += 1
        pack_gqa([x, g, x, g], kv_heads=2); self.hits["packgqa"] += 1
        persist_save([(x, g)], cap=2); self.hits["persistkv"] += 1
        cascade(x, [(x, g), (g, x), (x, x)], win=2); self.hits["cascade"] += 1
        epilogue(x, [g], x); self.hits["megafuse"] += 1
        pick(profile="mobile", seq=32, kv=40); self.hits["kselect"] += 1
        return self.card()

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-social",
            "names": list(self.NAMES),
            "hits": dict(self.hits),
            "n": len(self.NAMES),
            "cites": [dict(c) for c in CITES],
            "stored_prose": 0,
            "law": "cite-do-not-copy",
        }
