"""
gameforge.omega.delta_memory — Delta-attention (KDA) associative memory.

Implements the "attention is a lookup, folded into ONE fixed matrix" idea:
instead of an ever-growing key/value list (standard attention → O(n) storage &
scan), we keep a SINGLE fixed-size associative memory matrix ``M`` (dim×dim) and
CORRECT it with the delta rule (DeltaNet / KDA):

    k = embed(key)              # unit vector
    v = embed(value)            # target vector
    r = M @ k                   # current guess for this key
    Δ = v - r                   # the gap ("the delta is the gap")
    M = γ·M + β·(Δ ⊗ k)         # write ONLY the correction; rows fade via γ

Properties (from the KDA sketch):
  * Fixed footprint — same size at 1K or 1M writes (``dim×dim`` floats).
  * Write = correct the existing association, never append a new pair.
  * Rows fade over time (decay γ) so a fixed matrix never saturates.

This is a genuine linear-attention state (numpy), used as the Ω-fabric's
bounded working memory + a fast associative recall for Jeeves.
"""
from __future__ import annotations

import base64
import hashlib
import threading
import time
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

# A modality-tagged content payload: text string, or (modality, bytes/base64).
Content = Union[str, bytes]
MODALITIES = ("text", "image", "audio", "video", "vector")


def _bytes_of(content: Content, modality: str) -> bytes:
    """Coerce any modality's content to raw bytes for content-addressed embedding."""
    if isinstance(content, bytes):
        return content
    s = str(content)
    if modality in ("image", "audio", "video"):
        # strip data-URI header if present, then base64-decode
        if s.startswith("data:"):
            s = s.split(",", 1)[-1]
        try:
            return base64.b64decode(s, validate=False)
        except Exception:  # noqa: BLE001
            return s.encode("utf-8")
    return s.encode("utf-8")


def _embed(content: Content, dim: int, modality: str = "text") -> np.ndarray:
    """Deterministic unit-norm embedding for ANY modality via SHA-256 expansion.

    Text embeds from its UTF-8 bytes; image/audio/video embed from their decoded
    binary (content-addressed). A per-modality salt keeps the sub-spaces separable
    yet co-located in the SAME fixed matrix — one associative memory, all senses.
    """
    raw = _bytes_of(content, modality)
    salt = modality.encode("utf-8") + b":"
    # fold large binaries down to a stable 32-byte digest first (keeps it O(1))
    seed = hashlib.sha256(salt + raw).digest()
    vec = np.zeros(dim, dtype=np.float64)
    i = 0
    while i < dim:
        h = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
        chunk = np.frombuffer(h, dtype=np.uint8).astype(np.float64)
        take = min(len(chunk), dim - i)
        vec[i:i + take] = chunk[:take]
        i += take
    vec -= vec.mean()
    n = np.linalg.norm(vec)
    return vec / n if n > 1e-9 else vec


class DeltaMemory:
    """Fixed-size delta-rule associative memory (thread-safe)."""

    def __init__(self, dim: int = 64, beta: float = 0.6, decay: float = 0.999):
        self.dim = int(dim)
        self.beta = float(beta)          # learning rate for the correction
        self.decay = float(decay)        # γ — per-write row fade
        self.M = np.zeros((self.dim, self.dim), dtype=np.float64)
        self.writes = 0
        self.total_delta_energy = 0.0
        self._labels: List[str] = []     # bounded interpretability trail
        self.modality_writes: Dict[str, int] = {m: 0 for m in MODALITIES}
        self._lock = threading.Lock()

    # ── core delta rule (multimodal) ─────────────────────────────
    def write(self, key: Content, value: Content, modality: str = "text",
              key_modality: Optional[str] = None) -> Dict:
        """Fold a (key → value) association of ANY modality into the one matrix.
        ``modality`` tags the value; ``key_modality`` defaults to text so you can
        e.g. bind a text key to an IMAGE value (caption→picture) or vice-versa."""
        modality = modality if modality in MODALITIES else "text"
        kmod = key_modality if key_modality in MODALITIES else "text"
        k = _embed(key, self.dim, kmod)
        v = _embed(value, self.dim, modality)
        with self._lock:
            r = self.M @ k                          # current guess
            delta = v - r                           # the gap
            self.M *= self.decay                    # fade
            self.M += self.beta * np.outer(delta, k)  # write only the correction
            self.writes += 1
            self.modality_writes[modality] = self.modality_writes.get(modality, 0) + 1
            energy = float(np.linalg.norm(delta))
            self.total_delta_energy += energy
            label = key if isinstance(key, str) else f"<{kmod}:{hashlib.sha256(_bytes_of(key, kmod)).hexdigest()[:8]}>"
            self._labels.append(label)
            if len(self._labels) > 256:
                self._labels = self._labels[-256:]
        return {"key": label, "modality": modality, "delta_energy": round(energy, 4),
                "matrix_norm": round(float(np.linalg.norm(self.M)), 4),
                "writes": self.writes}

    def read(self, key: Content, key_modality: str = "text") -> Dict:
        kmod = key_modality if key_modality in MODALITIES else "text"
        k = _embed(key, self.dim, kmod)
        with self._lock:
            r = self.M @ k
        recall_strength = float(np.linalg.norm(r))
        best_label, best_sim = None, -1.0
        with self._lock:
            for lbl in dict.fromkeys(self._labels[-64:]):
                lk = _embed(lbl, self.dim, "text")
                resp = self.M @ lk
                denom = (np.linalg.norm(resp) * recall_strength) or 1.0
                sim = float(np.dot(resp, r) / denom)
                if sim > best_sim:
                    best_sim, best_label = sim, lbl
        return {"key": str(key)[:64], "recall_strength": round(recall_strength, 4),
                "nearest": best_label, "similarity": round(best_sim, 4)}

    def stats(self) -> Dict:
        with self._lock:
            norm = float(np.linalg.norm(self.M))
            spectral = float(np.linalg.norm(self.M, 2)) if self.writes else 0.0
            distinct = len(set(self._labels))
        return {
            "dim": self.dim, "capacity_floats": self.dim * self.dim,
            "beta": self.beta, "decay": self.decay,
            "writes": self.writes, "distinct_keys": distinct,
            "modality_writes": dict(self.modality_writes),
            "multimodal": sum(1 for m, c in self.modality_writes.items() if c > 0 and m != "text") > 0,
            "matrix_norm": round(norm, 4), "spectral_norm": round(spectral, 4),
            "avg_delta_energy": round(self.total_delta_energy / max(1, self.writes), 4),
            "footprint_note": "fixed size — identical at 1K or 1M writes, any modality",
        }

    def snapshot_heatmap(self, cells: int = 8) -> List[List[float]]:
        """Downsampled |M| heatmap (cells×cells) for a compact UI viz."""
        with self._lock:
            m = np.abs(self.M)
        block = max(1, self.dim // cells)
        out: List[List[float]] = []
        for i in range(cells):
            row = []
            for j in range(cells):
                blk = m[i * block:(i + 1) * block, j * block:(j + 1) * block]
                row.append(round(float(blk.mean()) if blk.size else 0.0, 4))
            out.append(row)
        return out

    # ── durable state (survives restart, like the fabric IQ) ──────
    def to_persist(self) -> Dict:
        with self._lock:
            return {"dim": self.dim, "beta": self.beta, "decay": self.decay,
                    "writes": self.writes, "total_delta_energy": self.total_delta_energy,
                    "modality_writes": dict(self.modality_writes),
                    "labels": self._labels[-128:], "M": self.M.tolist()}

    def load(self, doc: Dict):
        try:
            with self._lock:
                self.dim = int(doc.get("dim", self.dim))
                self.beta = float(doc.get("beta", self.beta))
                self.decay = float(doc.get("decay", self.decay))
                self.writes = int(doc.get("writes", 0))
                self.total_delta_energy = float(doc.get("total_delta_energy", 0.0))
                mw = doc.get("modality_writes")
                if isinstance(mw, dict):
                    self.modality_writes.update({k: int(v) for k, v in mw.items()})
                self._labels = list(doc.get("labels", []))
                m = doc.get("M")
                if m:
                    arr = np.asarray(m, dtype=np.float64)
                    if arr.shape == (self.dim, self.dim):
                        self.M = arr
        except Exception:  # noqa: BLE001
            pass


# Shared 64-dim delta memory (4096 floats — fixed forever).
delta_memory = DeltaMemory(dim=64)


__all__ = ["DeltaMemory", "delta_memory", "_embed"]
