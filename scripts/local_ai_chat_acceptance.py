#!/usr/bin/env python3
"""Opt-in, real authenticated local-only Jeeves chat and durable replay probe.

This never instantiates an inference provider or accepts an external URL.
Only the *already-attested* loopback backend may be contacted; redirects
and environment proxies are disabled. A write requires explicit operator
approval AND an existing owner-authenticated canonical conversation thread
and expected version. No credentials, prompt, response text, Docker inspect
documents or application records enter the machine-readable receipt.

The observed backend chat/replay is physical *chat-route* evidence only.
It does not independently certify reviewer authority, shared Mongo writer
epochs, coherent recovery, signatures, GPU offload or release.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

from scripts import local_ai_docker as host
from scripts import local_ai_offline_compose as binding
from scripts import local_ai_offline_launch as launch

SCHEMA = "skeleton.local-ai.docker.physical-local-chat-replay.v1"
THREAD = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
TOKEN = re.compile(r"[A-Za-z0-9._~+/\-=]{16,4096}\Z")
REF = re.compile(r"provider:local:[A-Za-z0-9._:/#@+-]{1,2048}\Z")
MAX_HTTP_BYTES = 262144
MAX_TOKEN_BYTES = 4096
MAX_OUTPUT_TOKENS = 96


class LocalChatProbeError(host.LocalDockerError):
    """Cannot independently admit a physical local-only chat operation."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalChatProbeError("local chat redirect is forbidden")


def _token(path: Path) -> str:
    if not isinstance(path, Path) or not path.is_absolute():
        raise LocalChatProbeError("authentication token path must be absolute")
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_uid != os.getuid()
                or before.st_mode & 0o077
                or not 16 <= before.st_size <= MAX_TOKEN_BYTES):
            raise LocalChatProbeError("authentication token file not owner-private")
        with os.fdopen(os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        ), "rb") as file:
            opened = os.fstat(file.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev, before.st_ino, before.st_size
            ):
                raise LocalChatProbeError("authentication token inode drift")
            raw = file.read(MAX_TOKEN_BYTES + 1)
        after = path.lstat()
        if (
            (after.st_dev, after.st_ino, after.st_size,
             after.st_mtime_ns, after.st_ctime_ns)
            != (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
        ):
            raise LocalChatProbeError("authentication token changed during read")
        value = raw.decode("ascii").rstrip("\n")
    except (OSError, UnicodeError):
        raise LocalChatProbeError("private local authentication token unavailable") from None
    if not TOKEN.fullmatch(value) or value != value.strip() or "\n" in value:
        raise LocalChatProbeError("authentication token format invalid")
    return value


def _endpoint(mode: str, root: Path) -> str:
    command = host.compose_command(mode, root)
    raw = host._run([*command, "config", "--format", "json"],
                    root=root, capture=True)
    if not isinstance(raw, str) or len(raw) > 2 * 1024 * 1024:
        raise LocalChatProbeError("effective local backend port unavailable")
    try:
        topology = json.loads(raw)
    except (TypeError, ValueError):
        raise LocalChatProbeError("effective backend topology malformed") from None
    host._validate_config(mode, topology)
    service = topology.get("services", {}).get("backend")
    ports = service.get("ports") if isinstance(service, dict) else None
    if not isinstance(ports, list):
        raise LocalChatProbeError("backend ingress must be explicit loopback")
    selected = []
    for row in ports:
        if not isinstance(row, dict):
            raise LocalChatProbeError("backend published port format invalid")
        if row.get("target") == 8001 and row.get("protocol", "tcp") == "tcp":
            if row.get("host_ip") != "127.0.0.1":
                raise LocalChatProbeError("backend ingress is not IPv4 loopback")
            published = row.get("published")
            if isinstance(published, bool) or not str(published).isdigit():
                raise LocalChatProbeError("backend published port format invalid")
            port = int(published)
            if not 1 <= port <= 65535:
                raise LocalChatProbeError("backend published port out of bounds")
            selected.append(port)
    if len(selected) != 1:
        raise LocalChatProbeError("exactly one private local backend port required")
    return "http://127.0.0.1:" + str(selected[0])


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, value in pairs:
        if key in data:
            raise LocalChatProbeError("duplicate backend JSON field")
        data[key] = value
    return data


def _http(base: str, token: str, method: str, path: str,
          *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if (not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", base)
            or method not in ("GET", "POST")
            or not path.startswith("/api/ai/")
            or "\r" in path or "\n" in path or "://" in path):
        raise LocalChatProbeError("untrusted backend HTTP destination")
    if not TOKEN.fullmatch(token):
        raise LocalChatProbeError("local authorization token unavailable")
    if method == "POST" and payload is None:
        raise LocalChatProbeError("POST to backend requires bounded request body")
    if method == "GET" and payload is not None:
        raise LocalChatProbeError("GET may not mutate or carry a body")
    data = None
    if payload is not None:
        try:
            data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True, allow_nan=False).encode("ascii")
        except (TypeError, ValueError):
            raise LocalChatProbeError("local chat payload invalid") from None
        if len(data) > 8192:
            raise LocalChatProbeError("local chat request byte limit exceeded")
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/json", "Cache-Control": "no-store"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base + path, data=data, headers=headers, method=method)
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=45 if method == "POST" else 8) as response:
            if (response.status != 200
                    or response.headers.get("Content-Type", "").split(";")[0].strip()
                    != "application/json"):
                raise LocalChatProbeError("backend returned unexpected HTTP envelope")
            body = response.read(MAX_HTTP_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        # Do not log remote diagnostics or HTTPError object: these may contain
        # sensitive response bodies, credentials and local conversation text.
        raise LocalChatProbeError("authenticated local backend request rejected") from None
    if not 0 < len(body) <= MAX_HTTP_BYTES:
        raise LocalChatProbeError("backend response exceeded bounded size")
    try:
        output = json.loads(body, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeError, ValueError, TypeError):
        raise LocalChatProbeError("backend response JSON invalid") from None
    if not isinstance(output, dict):
        raise LocalChatProbeError("backend returned non-object evidence")
    return output


def _admit_readiness(readiness: Mapping[str, Any],
                     providers: Mapping[str, Any]) -> None:
    checks = readiness.get("checks")
    if (readiness.get("schema_version") != "backend.ai.chat-readiness.v1"
            or readiness.get("available") is not True
            or not isinstance(checks, dict)
            or any(
                not isinstance(checks.get(name), dict)
                or checks[name].get("available") is not True
                for name in ("conversation_storage", "engine", "models")
            )):
        raise LocalChatProbeError("protected backend chat readiness not available")
    rows = providers.get("providers")
    if (providers.get("engine") != "skeleton-engine"
            or providers.get("active") != "local"
            or providers.get("llm_available") is not True
            or providers.get("availability_observed") is not True
            or not isinstance(rows, list)
            or len(rows) != 1):
        raise LocalChatProbeError("backend provider is not exclusive local Jeeves")
    only = rows[0]
    if (not isinstance(only, dict) or only.get("id") != "local"
            or only.get("model") != "jeeves"
            or only.get("available") is not True
            or only.get("ownership") != "engine-process"):
        raise LocalChatProbeError("backend provider inventory differs from local Jeeves")


def _observations(base: str, token: str) -> None:
    _admit_readiness(
        _http(base, token, "GET", "/api/ai/chat/readiness"),
        _http(base, token, "GET", "/api/ai/providers"),
    )


def _validate_original(data: Mapping[str, Any], marker: str) -> tuple[str, str]:
    if (data.get("success") is not True
            or data.get("ai_generated") is not True
            or data.get("provider") != "skeleton-engine"
            or data.get("engine_runtime_provider") != "local"
            or data.get("replayed") is not False):
        raise LocalChatProbeError("actual Jeeves chat turn not local and complete")
    response = data.get("response")
    if not isinstance(response, str) or response.strip() != marker:
        raise LocalChatProbeError("actual native Jeeves model did not reproduce challenge")
    receipts = data.get("engine_provider_receipts")
    if (not isinstance(receipts, list) or not 1 <= len(receipts) <= 128
            or any(not isinstance(ref, str) or not REF.fullmatch(ref)
                   for ref in receipts)
            or len(set(receipts)) != len(receipts)):
        raise LocalChatProbeError("engine provider receipt set not exclusively local")
    execution = data.get("engine_execution_id")
    operation = data.get("engine_operation_id")
    if (not isinstance(execution, str) or not 1 <= len(execution) <= 128
            or not isinstance(operation, str) or not 1 <= len(operation) <= 128):
        raise LocalChatProbeError("backend native execution identity unavailable")
    if data.get("turn_state") not in ("complete", "completed"):
        raise LocalChatProbeError("local assistant durable turn not committed")
    assistant = data.get("assistant_message")
    user = data.get("user_message")
    if (not isinstance(assistant, dict) or not isinstance(user, dict)
            or assistant.get("content") != response
            or not isinstance(assistant.get("message_id"), str)
            or not isinstance(user.get("message_id"), str)
            or assistant["message_id"] == user["message_id"]):
        raise LocalChatProbeError("assistant/user transcript identity unavailable")
    return execution, hashlib.sha256(response.encode("utf-8")).hexdigest()


def _validate_replay(original: Mapping[str, Any],
                     replay: Mapping[str, Any], marker: str) -> None:
    if (replay.get("success") is not True
            or replay.get("accepted") is not True
            or replay.get("terminal") is not True
            or replay.get("state") != "completed"
            or replay.get("provider") != "replayed"
            or replay.get("replayed") is not True
            or replay.get("ai_generated") is not True
            or replay.get("engine_runtime_provider") != "local"
            or replay.get("engine_execution_id") != original.get("engine_execution_id")
            or replay.get("response") != marker):
        raise LocalChatProbeError("durable local-only chat replay is not exact")
    receipts = replay.get("engine_provider_receipts")
    if (receipts != original.get("engine_provider_receipts")
            or not isinstance(receipts, list)):
        raise LocalChatProbeError("durable replay lost local provider custody")


def observe_local_chat(mode: str, archive: Path, overlay_directory: Path,
                       token_file: Path, *,
                       expected_receipt_sha256: str,
                       root: Path = host.ROOT) -> dict[str, Any]:
    """No chat mutation: attest already-running Docker and backend/readiness."""
    before = launch.attest_running_offline(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    if before.get("containers_observed") != 4:
        raise LocalChatProbeError("canonical four running containers unavailable")
    token = _token(token_file)
    base = _endpoint(mode, root)
    _observations(base, token)
    final = launch.attest_running_offline(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    if final != before:
        raise LocalChatProbeError("running container identities changed during chat probe")
    return {
        "schema": SCHEMA,
        "status": "local_chat_backend_readiness_observed_no_turn_executed",
        "mode": mode,
        "image_bundle_fingerprint": before["source_receipt_file_sha256"],
        "all_four_running_containers_verified": True,
        "exclusive_local_backend_provider_observed": True,
        "conversation_storage_readiness_observed": True,
        "native_model_turn_executed": False,
        "durable_chat_turn_written": False,
        "independent_active_tokenizer_attested": False,
        "independent_reviewer_attested": False,
        "majority_durable_writer_epoch_attested": False,
        "coherent_recovery_qualified": False,
        "protected_chat_qualified": False,
        "release_qualified": False,
    }


def qualify_local_chat(mode: str, archive: Path, overlay_directory: Path,
                       token_file: Path, *,
                       expected_receipt_sha256: str,
                       thread_id: str, expected_thread_version: int,
                       allow_durable_chat_turn: bool = False,
                       root: Path = host.ROOT) -> dict[str, Any]:
    """Explicit real backend chat write and independent canonical replay check.

    The operator must provision an EXISTING owned thread and expected version.
    This operation deliberately never creates/migrates a user identity or
    thread, never replays a failed request and never retries a POST that may
    have durably committed. A network timeout after POST leaves state needing
    read-only manual investigation.
    """
    if allow_durable_chat_turn is not True:
        raise LocalChatProbeError("explicit durable chat mutation approval required")
    if (not isinstance(thread_id, str) or not THREAD.fullmatch(thread_id)
            or type(expected_thread_version) is not int
            or not 1 <= expected_thread_version <= 2**31 - 1):
        raise LocalChatProbeError("canonical existing thread/version invalid")
    observed = observe_local_chat(
        mode, archive, overlay_directory, token_file,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    # Require the exact pinned engine's real local native preflight/turn,
    # independently of backend provider availability and container health.
    native = binding.qualify_offline_model(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    if native.get("model_turn_executed") is not True:
        raise LocalChatProbeError("real pinned native model one-shot unavailable")
    # Recheck the live target after potentially long model work.
    after = observe_local_chat(
        mode, archive, overlay_directory, token_file,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    if after != observed:
        raise LocalChatProbeError("local backend changed during native qualification")
    before_turn = launch.attest_running_offline(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    base = _endpoint(mode, root)
    token = _token(token_file)
    nonce = secrets.token_hex(16)
    marker = "SKL_OFFLINE_" + nonce
    prompt = (
        "Local-only Jeeves physical chat qualification. "
        "Reply with exactly this token, without formatting or commentary: "
        + marker
    )
    if hashlib.sha256(token.encode("ascii")).digest() != hashlib.sha256(
        _token(token_file).encode("ascii")
    ).digest():
        raise LocalChatProbeError("local authenticated principal changed before chat")
    key = "skl-offline-physical-" + nonce
    submission = _http(base, token, "POST", "/api/ai/chat",
                       payload={
                           "message": prompt,
                           "thread_id": thread_id,
                           "idempotency_key": key,
                           "expected_thread_version": expected_thread_version,
                           "provider_id": "local", "model_id": "jeeves",
                           "max_output_tokens": MAX_OUTPUT_TOKENS,
                           "temperature": 0.0,
                           "response_mode": "wait",
                       })
    execution, answer_hash = _validate_original(submission, marker)
    replay = _http(base, token, "GET",
                   "/api/ai/chat/turns/" + thread_id + "?"
                   + urlencode({"idempotency_key": key}))
    _validate_replay(submission, replay, marker)
    final = launch.attest_running_offline(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    if (final.get("containers") != before_turn.get("containers")
            or final.get("source_receipt_file_sha256")
            != before_turn.get("source_receipt_file_sha256")):
        raise LocalChatProbeError("canonical runtime changed after chat commitment")
    return {
        "schema": SCHEMA,
        "status": "real_local_chat_and_durable_replay_observed_not_full_guard_authority",
        "mode": mode,
        "source_receipt_file_sha256": observed["image_bundle_fingerprint"],
        "native_model_sha256": native["model_sha256"],
        "native_executable_sha256": native["executable_sha256"],
        "answer_sha256": answer_hash,
        "native_model_one_shot_executed": True,
        "authenticated_backend_local_chat_executed": True,
        "durable_canonical_replay_verified": True,
        "engine_execution_id_sha256": hashlib.sha256(execution.encode()).hexdigest(),
        "credentials_exposed": False,
        "prompt_or_response_text_in_receipt": False,
        "independent_active_tokenizer_attested": False,
        "independent_reviewer_attested": False,
        "majority_durable_writer_epoch_attested": False,
        "coherent_recovery_qualified": False,
        "physical_gpu_offload_qualified": False,
        "protected_chat_qualified": False,
        "release_qualified": False,
    }


__all__ = ["observe_local_chat", "qualify_local_chat"]
