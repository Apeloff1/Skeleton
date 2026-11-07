"""Fail-closed activation barrier for Compose-hosted native local inference.

This barrier does not initialize Mongo, migrate existing volumes, manufacture a
reviewer, or turn a standalone mongod into a replica set. It is deliberately
unusable until the operator has supplied a primary-backed canonical source
epoch, fenced owners, and an independently administered reviewer. Inference
remains unavailable on any ambiguous or stale observation.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch,
    MongoSourceEpochError,
    verify_canonical_source_writer_inventory,
)
from skeleton.provider_runtime import ProviderPolicyError
from .reviewer_custody import ReviewerCustodyError, ReviewerCustodyVerifier, ReviewerTrustAnchor

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PROBE_SECONDS = 5.0
_MAX_TOTAL_AUTHORITY_SECONDS = 10.0


class ActivationBlocked(ProviderPolicyError):
    """Protected inference cannot establish or retain its startup authority."""


class ActivationPhase(str, Enum):
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class ActivationPermit:
    """Single-generation evidence, not a bearer token or reusable capability."""

    generation: int
    tenant_id: str
    actor_id: str
    context_id: str
    epoch: int
    model_digest: str
    runtime_digest: str
    tokenizer_digest: str


def _role_custody(auth: object) -> tuple[tuple[str, str], ...]:
    """Bind role rotation without granting authorization from a status probe."""
    if type(auth) is not dict or type(auth.get("authInfo")) is not dict:
        raise ActivationBlocked("Mongo role custody unavailable")
    info = auth["authInfo"]
    # Missing role inventory is not authorization custody: a proxy must not
    # erase role rotation evidence by omitting this field during attestation.
    if "authenticatedUserRoles" not in info:
        raise ActivationBlocked("Mongo role custody unavailable")
    roles = info["authenticatedUserRoles"]
    if type(roles) is not list or len(roles) > 64:
        raise ActivationBlocked("Mongo role custody malformed")
    pairs: list[tuple[str, str]] = []
    for role in roles:
        if type(role) is not dict:
            raise ActivationBlocked("Mongo role custody malformed")
        db, name = role.get("db"), role.get("role")
        if (type(db) is not str or type(name) is not str
                or not db or not name or len(db) > 128 or len(name) > 128
                or not db.isascii() or not name.isascii()
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in db + name)):
            raise ActivationBlocked("Mongo role custody malformed")
        pairs.append((db, name))
    if len(set(pairs)) != len(pairs):
        raise ActivationBlocked("Mongo role custody duplicated")
    return tuple(sorted(pairs))


class MongoGuardedActivation:
    """Owner-scoped barrier with exact native artifact and Mongo epoch binding.

    A production composition root must supply the SAME Mongo database object
    used to construct the epoch and install that epoch on both canonical owners.
    A known-method inventory is checked, but external writers, replica-set
    membership and reviewer independence still require operational assurance.
    This object is not a replacement for the pre-delivery adversarial guard.
    """

    def __init__(
        self, *,
        database: Any,
        epoch: MongoCanonicalSourceEpoch,
        conversation: Any,
        memory: Any,
        backend: Any,
        reviewer: Any,
        reviewer_authority_id: str,
        reviewer_trust_anchor: ReviewerTrustAnchor,
        tenant_id: str,
        actor_id: str,
        context_id: str,
        expected_model_digest: str,
        expected_runtime_digest: str,
        expected_tokenizer_digest: str,
    ) -> None:
        from .native_transformer import NativeTransformerModel

        if type(epoch) is not MongoCanonicalSourceEpoch:
            raise ActivationBlocked("canonical Mongo epoch authority required")
        if getattr(epoch, "_database", None) is not database:
            raise ActivationBlocked("activation must use the canonical epoch database")
        if type(backend) is not NativeTransformerModel:
            raise ActivationBlocked("exact activated native transformer required")
        # A signer-only challenge callback is insufficient: the pre-delivery
        # reviewer verdict must itself use the pinned Ed25519 transport. A
        # callable that signs challenges but approves text locally is unsafe.
        from .signed_reviewer_client import SignedReviewerClient
        if type(reviewer) is not SignedReviewerClient or reviewer is backend:
            raise ActivationBlocked("signed independent reviewer client required")
        # The activation challenge and the actual pre-delivery verdict must
        # verify against one exact app-pinned key, authority and trust domain.
        # Separate anchors could let a challenge signer attest identity while
        # an unrelated verdict signer approves the generated text.
        if (type(reviewer_trust_anchor) is not ReviewerTrustAnchor
                or getattr(reviewer, "_anchor", None) != reviewer_trust_anchor):
            raise ActivationBlocked("signed reviewer verdict trust anchor mismatch")
        if (not isinstance(reviewer_authority_id, str)
                or not 1 <= len(reviewer_authority_id) <= 128
                or reviewer_authority_id != reviewer_authority_id.strip()
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in reviewer_authority_id)):
            raise ActivationBlocked("reviewer authority identity invalid")
        for value in (tenant_id, actor_id, context_id):
            # Strict UTF-8 is part of the persisted Mongo scope contract.
            # Lone surrogates cannot be serialized and must fail as policy
            # denial, not escape as a UnicodeEncodeError during first run.
            if type(value) is not str or not value or value != value.strip():
                raise ActivationBlocked("activation owner scope invalid")
            try:
                encoded = value.encode("utf-8", errors="strict")
            except UnicodeError:
                raise ActivationBlocked("activation owner scope invalid") from None
            if (len(encoded) > 512
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
                raise ActivationBlocked("activation owner scope invalid")
        for value in (expected_model_digest, expected_runtime_digest, expected_tokenizer_digest):
            if type(value) is not str or _HEX64.fullmatch(value) is None:
                raise ActivationBlocked("activated artifact digest invalid")
        if not callable(getattr(database, "command", None)):
            raise ActivationBlocked("Mongo replica-set authority unavailable")
        self._database = database
        self._epoch = epoch
        self._conversation = conversation
        self._memory = memory
        self._backend = backend
        self._reviewer = reviewer
        self._reviewer_authority_id = reviewer_authority_id
        self._reviewer_trust_anchor = reviewer_trust_anchor
        try:
            self._reviewer_verifier = ReviewerCustodyVerifier(
                reviewer=reviewer, authority_id=reviewer_authority_id,
                trust_anchor=reviewer_trust_anchor,
            )
        except ReviewerCustodyError:
            raise ActivationBlocked("independent reviewer trust anchor required") from None
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._context_id = context_id
        self._identity = (
            expected_model_digest, expected_runtime_digest, expected_tokenizer_digest,
        )
        self._phase = ActivationPhase.BLOCKED
        self._generation = 0
        self._epoch_at_activation: int | None = None
        self._auth_at_activation: tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]] | None = None
        self._lock = asyncio.Lock()

    @property
    def phase(self) -> ActivationPhase:
        return self._phase

    def _verify_reviewer_binding(self) -> None:
        # A mutable client reconfigured after startup must not switch verdict
        # verification to a different signer while activation challenges
        # continue to be verified against the original pinned public key.
        if (getattr(self._reviewer, "_anchor", None)
                != self._reviewer_trust_anchor):
            raise ActivationBlocked("reviewer trust anchor changed during activation")

    def _verify_backend(self) -> None:
        try:
            backend = self._backend
            backend.assert_identity()
            tokenizer = backend.runtime.tokenizer
            tokenizer.assert_unchanged()
            current = (backend.model_digest, backend.runtime_digest, tokenizer.digest)
            if current != self._identity:
                raise ActivationBlocked("activated model or tokenizer changed")
        except ActivationBlocked:
            raise
        except Exception:
            raise ActivationBlocked("native model/tokenizer identity unavailable") from None

    async def _probe(self) -> tuple[int, tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]]: 
        try:
            async with asyncio.timeout(_MAX_TOTAL_AUTHORITY_SECONDS):
                return await self._probe_bounded()
        except TimeoutError:
            raise ActivationBlocked("guarded activation authority timed out") from None

    async def _probe_bounded(self) -> tuple[int, tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]]: 
        try:
            async with asyncio.timeout(_MAX_PROBE_SECONDS):
                hello = await self._database.command("hello")
            if (type(hello) is not dict
                    or type(hello.get("setName")) is not str
                    or not hello["setName"]
                    or hello.get("isWritablePrimary") is not True):
                raise ActivationBlocked("linearizable Mongo replica-set primary required")
            topology_fields = ("setName", "me", "primary", "electionId", "setVersion")
            # Never compare attacker-controlled BSON objects with custom equality.
            # Mongo hello topology identifiers have a narrow primitive contract;
            # ObjectId election identifiers are permitted, but arbitrary Python
            # equality hooks must not decide whether an election occurred.
            def topology_identity(observation: dict) -> tuple:
                from bson.objectid import ObjectId
                values = []
                for field in topology_fields:
                    value = observation.get(field)
                    allowed = (str, type(None)) if field in ("setName", "me", "primary") else (int, type(None))
                    if field == "electionId":
                        allowed = (ObjectId, type(None))
                    if type(value) not in allowed:
                        raise ActivationBlocked("Mongo topology identity malformed")
                    if type(value) is str and (not value or len(value) > 512 or not value.isascii()
                            or any(ord(ch) < 33 or ord(ch) > 126 for ch in value)):
                        raise ActivationBlocked("Mongo topology identity malformed")
                    if type(value) is int and not 0 <= value <= 2147483647:
                        raise ActivationBlocked("Mongo topology identity malformed")
                    values.append(value)
                return tuple(values)
            initial_topology = topology_identity(hello)
            # A replica-set primary can be reachable with authentication
            # disabled. A linearizable epoch on an unauthenticated server
            # cannot establish trusted custody for protected local inference.
            # Inspect the actual connection; never accept an environment
            # flag, client-supplied username or successful ping as identity.
            async with asyncio.timeout(_MAX_PROBE_SECONDS):
                auth = await self._database.command("connectionStatus")
            users = (
                auth.get("authInfo", {}).get("authenticatedUsers")
                if type(auth) is dict and type(auth.get("authInfo")) is dict
                else None
            )
            if (type(users) is not list or not users
                    or any(
                        type(user) is not dict
                        or type(user.get("user")) is not str or not user["user"]
                        or type(user.get("db")) is not str or not user["db"]
                        for user in users
                    )):
                raise ActivationBlocked("authenticated canonical Mongo session required")
            # Duplicate principals and unbounded identity material cannot
            # establish a unique, bounded authenticated authority snapshot.
            # Reject rather than silently normalizing duplicates by sorting.
            if (len(users) > 16 or any(
                    len(user["user"]) > 128 or len(user["db"]) > 128
                    or any(ord(ch) < 33 or ord(ch) > 126
                           for ch in user["user"] + user["db"])
                    for user in users)):
                raise ActivationBlocked("Mongo authenticated principal invalid")
            if len({(user["db"], user["user"]) for user in users}) != len(users):
                raise ActivationBlocked("Mongo authenticated principal duplicated")
            # Pin the exact authenticated Mongo principal set across the
            # entire activation generation. A silent credential or identity
            # swap must require explicit operator reactivation, even if the
            # epoch happens to have the same numeric value.
            auth_identity = tuple(sorted((user["db"], user["user"]) for user in users))
            role_identity = _role_custody(auth)
            # The backend and engine may use different logical databases on
            # the same Mongo server. A seqlock in one database does not fence
            # canonical writes in another database or another client.
            db_name = getattr(self._database, "name", None)
            db_client = getattr(self._database, "client", None)
            if type(db_name) is not str or not db_name or db_client is None:
                raise ActivationBlocked("canonical Mongo database identity missing")
            collections = (
                getattr(self._epoch, "_collection", None),
                getattr(self._epoch, "_reader", None),
                getattr(self._conversation, "threads", None),
                getattr(self._conversation, "messages", None),
                getattr(self._memory, "records", None),
                getattr(self._memory, "idempotency", None),
                getattr(self._memory, "revisions", None),
                getattr(self._memory, "projection_outbox", None),
            )
            for collection in collections:
                owner = getattr(collection, "database", None)
                if (getattr(owner, "name", None) != db_name
                        or getattr(owner, "client", None) is not db_client):
                    raise ActivationBlocked("canonical source database ownership mismatch")
            verify_canonical_source_writer_inventory(
                conversation=self._conversation, memory=self._memory, epoch=self._epoch,
            )
            self._verify_backend()
            self._verify_reviewer_binding()
            first_epoch = await self._epoch.read_epoch(
                tenant_id=self._tenant_id,
                actor_id=self._actor_id,
                context_id=self._context_id,
            )
            await self._reviewer_verifier.verify(
                tenant_id=self._tenant_id, actor_id=self._actor_id,
                context_id=self._context_id, epoch=first_epoch,
                model_digest=self._identity[0],
                runtime_digest=self._identity[1],
                tokenizer_digest=self._identity[2],
            )
            self._verify_reviewer_binding()
            # The reviewer round trip is an await boundary: the Mongo primary
            # or authenticated connection identity could rotate while a
            # signature is in flight. A matching epoch alone is insufficient.
            async with asyncio.timeout(_MAX_PROBE_SECONDS):
                final_hello = await self._database.command("hello")
                final_auth = await self._database.command("connectionStatus")
            if (type(final_hello) is not dict
                    or final_hello.get("isWritablePrimary") is not True
                    or topology_identity(final_hello)
                    != initial_topology):
                raise ActivationBlocked("Mongo primary changed during reviewer attestation")
            final_users = (
                final_auth.get("authInfo", {}).get("authenticatedUsers")
                if type(final_auth) is dict
                and type(final_auth.get("authInfo")) is dict else None
            )
            if (type(final_users) is not list or not final_users
                    or any(type(user) is not dict
                           or type(user.get("user")) is not str or not user["user"]
                           or type(user.get("db")) is not str or not user["db"]
                           for user in final_users)
                    or len(final_users) > 16
                    or any(len(user["user"]) > 128 or len(user["db"]) > 128
                           or any(ord(ch) < 33 or ord(ch) > 126
                                  for ch in user["user"] + user["db"])
                           for user in final_users)
                    or len({(user["db"], user["user"]) for user in final_users}) != len(final_users)
                    or tuple(sorted((user["db"], user["user"]) for user in final_users))
                    != auth_identity or _role_custody(final_auth) != role_identity):
                raise ActivationBlocked("Mongo principal changed during reviewer attestation")
            # A canonical writer may enter WRITING while the reviewer signs.
            # A second linearizable read is required after that await.
            final_epoch = await self._epoch.read_epoch(
                tenant_id=self._tenant_id,
                actor_id=self._actor_id,
                context_id=self._context_id,
            )
            if final_epoch != first_epoch:
                raise ActivationBlocked("canonical source changed during reviewer attestation")
            # The final linearizable read is another await boundary. A primary
            # election or authenticated principal rotation during that read
            # must not turn a previously verified reviewer proof into a permit.
            async with asyncio.timeout(_MAX_PROBE_SECONDS):
                post_epoch_hello = await self._database.command("hello")
                post_epoch_auth = await self._database.command("connectionStatus")
            if (type(post_epoch_hello) is not dict
                    or post_epoch_hello.get("isWritablePrimary") is not True
                    or topology_identity(post_epoch_hello)
                    != initial_topology):
                raise ActivationBlocked("Mongo primary changed during final epoch read")
            post_users = (
                post_epoch_auth.get("authInfo", {}).get("authenticatedUsers")
                if type(post_epoch_auth) is dict
                and type(post_epoch_auth.get("authInfo")) is dict else None
            )
            if (type(post_users) is not list or not post_users
                    or any(type(user) is not dict
                           or type(user.get("user")) is not str or not user["user"]
                           or type(user.get("db")) is not str or not user["db"]
                           for user in post_users)
                    or len(post_users) > 16
                    or any(len(user["user"]) > 128 or len(user["db"]) > 128
                           or any(ord(ch) < 33 or ord(ch) > 126
                                  for ch in user["user"] + user["db"])
                           for user in post_users)
                    or len({(user["db"], user["user"]) for user in post_users}) != len(post_users)
                    or tuple(sorted((user["db"], user["user"]) for user in post_users))
                    != auth_identity or _role_custody(post_epoch_auth) != role_identity):
                raise ActivationBlocked("Mongo principal changed during final epoch read")
            # The final Mongo authority observations await I/O. Re-check the
            # independent verdict trust anchor at the last permit boundary:
            # a mutable reviewer transport must not rotate its verifier while
            # the epoch and primary are being revalidated.
            self._verify_reviewer_binding()
            self._verify_backend()
            return final_epoch, (auth_identity, role_identity)
        except ActivationBlocked:
            raise
        except ReviewerCustodyError:
            raise ActivationBlocked("independent reviewer custody unavailable") from None
        except (MongoSourceEpochError, TimeoutError):
            raise ActivationBlocked("canonical source epoch unavailable") from None
        except Exception:
            raise ActivationBlocked("protected activation authority unavailable") from None

    async def activate(self) -> ActivationPermit:
        """Explicit startup; never provisions an epoch or performs migration."""
        async with self._lock:
            if self._phase is ActivationPhase.REVOKED:
                raise ActivationBlocked("revoked activation cannot restart in place")
            self._phase = ActivationPhase.VERIFYING
            self._generation += 1
            generation = self._generation
            try:
                epoch, auth_identity = await self._probe()
            except BaseException:
                self._phase = ActivationPhase.BLOCKED
                self._epoch_at_activation = None
                self._auth_at_activation = None
                raise
            self._epoch_at_activation = epoch
            self._auth_at_activation = auth_identity
            self._phase = ActivationPhase.ACTIVE
            return ActivationPermit(
                generation, self._tenant_id, self._actor_id, self._context_id,
                epoch, *self._identity,
            )

    async def assert_active(self, permit: ActivationPermit | None = None) -> ActivationPermit:
        """Revalidate before dispatch AND after generation, including revocations.

        A stable epoch change also blocks inference: even a legitimate writer
        changes the canonical source and needs a fresh explicit activation.
        """
        async with self._lock:
            if self._phase is not ActivationPhase.ACTIVE:
                raise ActivationBlocked("guarded local inference is not activated")
            generation = self._generation
            epoch_at_activation = self._epoch_at_activation
            auth_at_activation = self._auth_at_activation
            expected = ActivationPermit(
                generation, self._tenant_id, self._actor_id, self._context_id,
                epoch_at_activation, *self._identity,
            )
            if permit is not None and (type(permit) is not ActivationPermit or permit != expected):
                raise ActivationBlocked("activation permit is stale or mismatched")
        try:
            epoch, auth_identity = await self._probe()
        except BaseException:
            async with self._lock:
                # A failed or cancelled probe belongs only to its captured
                # generation. Another task may have already blocked and
                # explicitly reactivated a newer generation while this probe
                # was awaiting Mongo or the independent reviewer.
                if (self._phase is ActivationPhase.ACTIVE
                        and self._generation == generation):
                    self._phase = ActivationPhase.BLOCKED
                    self._generation += 1
                    self._epoch_at_activation = None
                    self._auth_at_activation = None
            raise
        async with self._lock:
            if (self._phase is not ActivationPhase.ACTIVE
                    or self._generation != generation
                    or self._epoch_at_activation != epoch
                    or epoch != epoch_at_activation
                    or auth_identity != auth_at_activation):
                # A concurrent operator revocation is terminal, not a
                # recoverable BLOCKED state that activate() may later reset.
                if (self._phase is ActivationPhase.ACTIVE
                        and self._generation == generation):
                    self._phase = ActivationPhase.BLOCKED
                    self._generation += 1
                    self._epoch_at_activation = None
                    self._auth_at_activation = None
                raise ActivationBlocked("canonical authority changed during inference")
            return expected

    async def revoke(self) -> None:
        """Local irrevocable hold. Global revocation needs an audited Mongo write."""
        async with self._lock:
            self._phase = ActivationPhase.REVOKED
            self._generation += 1
            self._epoch_at_activation = None
            self._auth_at_activation = None



async def compose_mongo_guarded_native_adapter(
    runtime: Any, *,
    database: Any,
    epoch: MongoCanonicalSourceEpoch,
    conversation: Any,
    memory: Any,
    snapshots: Any,
    reviewer: Any,
    reviewer_authority_id: str,
    reviewer_trust_anchor: ReviewerTrustAnchor,
    tenant_id: str,
    actor_id: str,
    context_id: str,
    operator_model_digest: str,
    operator_runtime_digest: str,
    operator_tokenizer_digest: str,
    model_id: str = "skeleton-native-transformer",
    cache_size: int = 128,
    default_seed: int = 0,
    max_concurrency: int = 1,
    max_queue_size: int = 256,
    max_batch_size: int = 256,
):
    """Build an activated, guarded native adapter; never create an unguarded one.

    This is a trusted application composition entrypoint, NOT a client-facing
    API. The caller must already have provisioned Mongo replica-set custody,
    independently reviewed writer coverage and a trusted reviewer. The factory
    refuses to provision epochs, modify Compose or silently select a model.
    """
    from .native_transformer import NativeTransformerModel
    from .native_guard_binding import native_transformer_guard_components
    from .guarded_composition import compose_protected_local_adapter
    from .local import LocalInferenceEngine

    backend = NativeTransformerModel(runtime, model_id=model_id)
    gate = MongoGuardedActivation(
        database=database, epoch=epoch, conversation=conversation, memory=memory,
        backend=backend, reviewer=reviewer,
        reviewer_authority_id=reviewer_authority_id,
        reviewer_trust_anchor=reviewer_trust_anchor,
        tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
        # Operator pins MUST originate from a trusted, independently reviewed
        # activation manifest. Using backend-derived digests as the expected
        # values is a self-attestation that silently accepts swapped weights
        # or a different tokenizer after restart.
        expected_model_digest=operator_model_digest,
        expected_runtime_digest=operator_runtime_digest,
        expected_tokenizer_digest=operator_tokenizer_digest,
    )
    await gate.activate()
    try:
        components = native_transformer_guard_components(
            backend, snapshots=snapshots, reviewer=reviewer,
        )
        engine = LocalInferenceEngine(
            backend, cache_size=cache_size, max_concurrency=max_concurrency,
            max_queue_size=max_queue_size, max_batch_size=max_batch_size,
            require_guarded_context=True,
        )
        return compose_protected_local_adapter(
            engine, components=components, default_seed=default_seed,
            activation_gate=gate,
            artifact_status={
                "kind": "native_transformer",
                "model_digest": backend.model_digest,
                "runtime_digest": backend.runtime_digest,
                "tokenizer_digest": backend.runtime.tokenizer.digest,
                "architecture_digest": runtime.architecture.digest,
                "device": runtime.device.to_dict(),
                "generation_limits": backend.generation_limits(),
            },
        )
    except BaseException:
        # An incomplete composition must not leave a live activation.
        await gate.revoke()
        raise

__all__ = [
    "ActivationBlocked", "ActivationPhase", "ActivationPermit", "MongoGuardedActivation",
    "compose_mongo_guarded_native_adapter",
]
