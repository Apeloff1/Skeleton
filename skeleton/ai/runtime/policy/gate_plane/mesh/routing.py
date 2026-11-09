"""Sticky + load-aware endpoint selection and a mesh-aware s2s client.

* **Sticky routing** — weighted rendezvous (HRW) hashing on a sticky key
  (tenant, conversation, session). Every endpoint gets a score
  ``-weight / ln(hash01(key, endpoint))``; the highest healthy score wins.
  Adding or losing an endpoint only remaps the keys that lived on it, and a
  key whose home peer is ejected lands on its *second* choice and moves
  back home when the peer recovers.
* **Unkeyed calls** — power-of-two-choices on in-flight count (ties by
  weight), seeded RNG for deterministic tests.
* **Zone preference** — optional: endpoints in ``local_zone`` are tried
  first while at least one is available.

:class:`MeshClient` runs a call through a Pack F :class:`Pipeline`; each
attempt (including retries issued by the retry stage) picks an endpoint,
excluding ones that already failed this call, so a retry goes to a
different peer. Outcomes feed passive outlier detection.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Callable, List, Optional, Sequence, Set

from skeleton.gate_plane.mesh.peers import Endpoint, PeerHealth, PeerSet
from skeleton.gate_plane.pipeline.core import CallContext, Pipeline, PipelineRequest, PipelineResponse
from skeleton.gate_plane.pipeline.errors import PipelineError
from skeleton.gate_plane.pipeline.retry import RetrySpec, Verdict

STICKY_HEADER = "x-s2s-sticky"


class NoEndpointAvailable(PipelineError):
    status = 503
    reason = "no_endpoint_available"


def _hash01(key: str, endpoint_id: str) -> float:
    digest = hashlib.blake2b(f"{key}\x00{endpoint_id}".encode("utf-8"), digest_size=8).digest()
    n = int.from_bytes(digest, "big")
    return (n + 1) / (2**64 + 1)  # open interval (0, 1)


def rendezvous_rank(key: str, peers: Sequence[PeerHealth]) -> List[PeerHealth]:
    def score(h: PeerHealth) -> float:
        return -h.endpoint.weight / math.log(_hash01(key, h.endpoint.id))

    return sorted(peers, key=lambda h: (score(h), h.endpoint.id), reverse=True)


class Selector:
    def __init__(self, peers: PeerSet, *, local_zone: Optional[str] = None, rng: Optional[random.Random] = None) -> None:
        self.peers = peers
        self.local_zone = local_zone
        self.rng = rng or random.Random()

    def _candidates(self, exclude: Set[str]) -> List[PeerHealth]:
        avail = [h for h in self.peers.available() if h.endpoint.id not in exclude]
        if self.local_zone is not None:
            local = [h for h in avail if h.endpoint.zone == self.local_zone]
            if local:
                return local
        return avail

    def pick(self, *, sticky_key: Optional[str] = None, exclude: Optional[Set[str]] = None) -> Optional[Endpoint]:
        cands = self._candidates(exclude or set())
        if not cands:
            return None
        if sticky_key:
            return rendezvous_rank(sticky_key, cands)[0].endpoint
        if len(cands) == 1:
            return cands[0].endpoint
        a, b = self.rng.sample(cands, 2)

        def load(h: PeerHealth) -> float:
            return h.in_flight / h.endpoint.weight

        if load(a) == load(b):
            return (a if a.endpoint.weight >= b.endpoint.weight else b).endpoint
        return (a if load(a) < load(b) else b).endpoint


Send = Callable[[Endpoint, PipelineRequest, CallContext], PipelineResponse]


class MeshClient:
    def __init__(
        self,
        peers: PeerSet,
        pipeline: Pipeline,
        send: Send,
        *,
        selector: Optional[Selector] = None,
        spec: Optional[RetrySpec] = None,
    ) -> None:
        self.peers = peers
        self.pipeline = pipeline
        self.send = send
        self.selector = selector or Selector(peers)
        self.spec = spec or RetrySpec()

    @staticmethod
    def sticky_key_for(request: PipelineRequest) -> Optional[str]:
        for k, v in request.headers.items():
            if str(k).lower() == STICKY_HEADER and str(v).strip():
                return str(v).strip()
        return request.tenant_id

    def call(
        self,
        request: PipelineRequest,
        *,
        sticky_key: Optional[str] = None,
        ctx: Optional[CallContext] = None,
    ) -> PipelineResponse:
        key = sticky_key if sticky_key is not None else self.sticky_key_for(request)
        tried: Set[str] = set()
        context = ctx or self.pipeline.new_context()
        context.attrs["endpoints"] = []

        def handler(req: PipelineRequest, c: CallContext) -> PipelineResponse:
            ep = self.selector.pick(sticky_key=key, exclude=tried)
            if ep is None and tried:
                ep = self.selector.pick(sticky_key=key)  # every peer tried: allow a repeat
            if ep is None:
                raise NoEndpointAvailable(f"no endpoint for {self.peers.service}")
            tried.add(ep.id)
            c.attrs["endpoints"].append(ep.id)
            c.attrs["endpoint"] = ep.id
            self.peers.acquire(ep.id)
            try:
                resp = self.send(ep, req, c)
            except Exception as exc:
                if not isinstance(exc, PipelineError) or self.spec.classify_error(exc) is Verdict.RETRYABLE:
                    self.peers.record_result(ep.id, False)
                raise
            finally:
                self.peers.release(ep.id)
            verdict = self.spec.classify_response(resp)
            self.peers.record_result(ep.id, verdict in (Verdict.SUCCESS, Verdict.CLIENT_ERROR))
            return resp

        return self.pipeline.run(request, handler, ctx=context)


__all__ = ["MeshClient", "NoEndpointAvailable", "STICKY_HEADER", "Selector", "rendezvous_rank"]
