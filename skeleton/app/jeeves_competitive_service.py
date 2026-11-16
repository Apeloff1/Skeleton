"""Authenticated local chat's advanced execution boundary.

All requests use the existing session identity, SQLite authority, and
single-inference lease. Auxiliary models cannot become primary chat
providers. Media and speculative results are deliberately review-only.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from hashlib import sha256
import time

from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig,RuntimeContractError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import OfflineAISession,OfflineAIError
from skeleton.app.jeeves_ensemble import SpecialistRegistry,run_ensemble
from skeleton.app.jeeves_native_media import LocalMediaRegistry
from skeleton.app.jeeves_prefetch import PredictiveReferenceCache
from skeleton.app.jeeves_tool_campaign import LocalToolCampaign,ToolCampaignConflict,ToolCampaignError
from skeleton.app.jeeves_local_lease import LocalInferenceLeaseBusy,LocalInferenceLeaseUnavailable
from skeleton.app.offline_grounding import normalized_document_scope

ACTIONS=frozenset({"ensemble-review","speculative-review","media-review","predictive-prefetch",
                   "tool-campaign-run","tool-campaign-inspect","tool-campaign-abandon"})


def _error(status,message):
    from skeleton.app.offline_http import OfflineHTTPError
    return OfflineHTTPError(status,message)


def _fields(body,required,optional=()):
    if type(body) is not dict or not set(required)<=set(body)<=set(required)|set(optional):
        raise _error(400,"invalid advanced local request fields")


def _int(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:
        raise _error(400,"invalid advanced execution budget")
    return value


def _text(value,limit):
    if type(value) is not str or not value.strip() or "\x00" in value or len(value.encode())>limit:
        raise _error(400,"bounded question required")
    return value.strip()


class CompetitiveService:
    def __init__(self,app,*,specialists=None,media=None):
        if specialists is not None and not isinstance(specialists,SpecialistRegistry):
            raise ValueError("explicit pinned specialist registry required")
        if media is not None and not isinstance(media,LocalMediaRegistry):
            raise ValueError("explicit pinned media registry required")
        self.app=app
        self.specialists=specialists
        self.media=media
        self.prefetch=PredictiveReferenceCache(app.knowledge)
        self.tools=LocalToolCampaign(app._store,app.knowledge,app.model_digest,app.tokenizer_digest)

    def status(self):
        runtime=self.app.backend.runtime if isinstance(self.app.backend,NativeRuntimeLocalModel) else None
        speculative=(runtime is not None and runtime.device.actual=="cpu"
                     and not runtime.model.resident and runtime.model._accel is None and not runtime.model.use_mod)
        return {"schema":"skeleton.jeeves.competitive-capabilities.v1",
                "primary_model_digest":self.app.model_digest,
                "specialists":[] if self.specialists is None else self.specialists.inventory(),
                "specialist_registry_sha256":None if self.specialists is None else self.specialists.identity,
                "media_profiles":[] if self.media is None else self.media.inventory(),
                "media_registry_sha256":None if self.media is None else self.media.identity,
                "native_greedy_speculative_target":speculative,
                "predictive_prefetch_available":self.app.knowledge._semantic_ranker is None and not self.app._semantic_multihop,
                "prefetch":self.prefetch.stats(),"tool_capabilities":["search","calculate","document_identity"],
                "maximum_tool_calls":8,"primary_model_changed":False,"network_called":False,
                "transcript_committed":False}

    def clear(self):
        self.prefetch.clear()

    @contextmanager
    def _generation(self,sid):
        app=self.app
        with app._turn_lock:
            if app._closing or app._active_session is not None:
                raise _error(409,"another local generation is running")
            app._active_session=sid
        try:
            with app._lock:
                app._admit_local_generation()
                with app._inference_lease.hold():
                    yield
        except LocalInferenceLeaseBusy:
            raise _error(423,"another local service owns the inference slot") from None
        except LocalInferenceLeaseUnavailable:
            raise _error(503,"private local inference lease unavailable") from None
        finally:
            with app._turn_lock:
                app._active_session=None

    def _snapshot(self,sid,revision):
        _int(revision,0,2**63-1)
        saved=self.app._session(sid)
        if saved.revision!=revision:
            raise _error(409,"conversation revision changed")
        rows=saved.transcript.to_list()
        def recheck():
            current=self.app._session(sid)
            if current.revision!=revision or current.transcript.to_list()!=rows:
                raise _error(409,"conversation changed during advanced operation")
        return rows,recheck

    def dispatch(self,sid,action,body):
        app=self.app
        if action=="tool-campaign-inspect":
            _fields(body,{"campaign_id"})
            try:
                return self.tools.inspect(sid,body["campaign_id"])
            except ToolCampaignConflict as exc:
                raise _error(409,str(exc)) from None
            except ToolCampaignError as exc:
                raise _error(400,str(exc)) from None
        if body.get("approved") is not True:
            raise _error(403,"this advanced local operation requires explicit approval")
        if action=="tool-campaign-abandon":
            _fields(body,{"campaign_id","plan_sha256","approved"})
            try:
                return self.tools.abandon(sid,body["campaign_id"],body["plan_sha256"])
            except ToolCampaignConflict as exc:
                raise _error(409,str(exc)) from None
            except ToolCampaignError as exc:
                raise _error(400,str(exc)) from None
        if action=="tool-campaign-run":
            _fields(body,{"campaign_id","expected_revision","plan","approved"})
            # Tool plans are finite read-only functions. No model or inference
            # lease is needed; shared store transactions fence the receipts.
            try:
                return self.tools.run(sid,body["campaign_id"],body["expected_revision"],body["plan"])
            except ToolCampaignConflict as exc:
                raise _error(409,str(exc)) from None
            except (ToolCampaignError,RuntimeContractError,ValueError):
                raise _error(400,"local tool plan rejected") from None
        if action=="predictive-prefetch":
            _fields(body,{"expected_revision","candidates","document_ids","approved"},{"maximum_queries"})
            if not self.status()["predictive_prefetch_available"]:
                raise _error(422,"prefetch currently requires exact lexical retrieval, not mutable ANN ranking")
            with app._lock:
                if app._closing:
                    raise _error(409,"local service closing")
                rows,recheck=self._snapshot(sid,body["expected_revision"])
                try:
                    return self.prefetch.warm(sid,body["expected_revision"],rows,body["candidates"],
                        body["document_ids"],maximum_queries=body.get("maximum_queries",2),
                        search=app._grounding_hits,recheck=recheck)
                except (ValueError,RuntimeContractError):
                    raise _error(422,"scoped relevance prefetch rejected") from None
        if action=="media-review":
            _fields(body,{"expected_revision","profile","media_type","media_base64","source_sha256","approved"},{"top_k"})
            if self.media is None:
                raise _error(422,"no pinned local media classifier configured")
            # Serialize actual model allocation with canonical local inference.
            with self._generation(sid):
                _,recheck=self._snapshot(sid,body["expected_revision"])
                try:
                    result=self.media.infer(body["profile"],
                        {k:body[k] for k in ("media_type","media_base64","source_sha256")},
                        top_k=body.get("top_k",2))
                except Exception:
                    raise _error(422,"local media decoding or classifier rejected") from None
                recheck()
                return result
        if action=="ensemble-review":
            _fields(body,{"expected_revision","message","profiles","max_output_tokens",
                          "maximum_reserved_tokens","approved"})
            if self.specialists is None:
                raise _error(422,"no pinned local specialist registry configured")
            question=_text(body["message"],1024)
            budget=_int(body["max_output_tokens"],1,128)
            maximum=_int(body["maximum_reserved_tokens"],1,384)
            with self._generation(sid):
                rows,recheck=self._snapshot(sid,body["expected_revision"])
                system=next((r["content"] for r in rows if r["role"]=="system"),"")
                history=tuple((r["role"],r["content"]) for r in rows if r["role"]!="system")
                def fence():
                    recheck()
                    app._admit_local_generation()
                try:
                    result=asyncio.run(run_ensemble(app.backend,self.specialists,body["profiles"],
                        question,history=history,instructions=system,revision=body["expected_revision"],
                        budget=budget,maximum_reserved=maximum,recheck=fence))
                except (ValueError,RuntimeContractError,RuntimeError,TimeoutError,OSError):
                    raise _error(422,"local ensemble incomplete; no candidate selected") from None
                fence()
                return result
        if action=="speculative-review":
            _fields(body,{"expected_revision","message","draft_profile","max_output_tokens","approved"},{"block"})
            if not self.status()["native_greedy_speculative_target"] or self.specialists is None:
                raise _error(422,"native CPU target and pinned compatible draft required")
            question=_text(body["message"],1024)
            budget=_int(body["max_output_tokens"],1,128)
            block=_int(body.get("block",4),1,8)
            with self._generation(sid):
                rows,recheck=self._snapshot(sid,body["expected_revision"])
                local=OfflineAISession(app.backend)
                local.instructions=next((r["content"] for r in rows if r["role"]=="system"),"")
                local.history=tuple((r["role"],r["content"]) for r in rows if r["role"]!="system")
                try:
                    request,_=local._request(question,budget,require_full_history=True)
                    draft=self.specialists.load(body["draft_profile"],primary_digest=app.model_digest,
                                               required_role="draft")
                    from skeleton.app.jeeves_speculative import generate_speculative
                    started=time.monotonic()
                    def fence():
                        # Per-inference cancellation/deadline check does not
                        # re-read SQLite for every transformer layer.
                        if time.monotonic()-started>45:
                            raise TimeoutError("speculative execution deadline")
                        if app._closing:
                            raise RuntimeContractError("local service closing")
                    result=generate_speculative(app.backend.runtime,draft,request.rendered_input,
                        GenerationConfig(max_new_tokens=budget,temperature=0,use_cache=False),
                        block=block,interrupt=fence)
                except (ValueError,RuntimeContractError,RuntimeError,TimeoutError,OSError):
                    raise _error(422,"native speculative review rejected") from None
                recheck()
                app._admit_local_generation()
                return result
        raise _error(404,"unknown competitive local operation")
