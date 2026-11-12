#!/usr/bin/env python3
"""Advanced Jeeves local acceptance: real GGUF, HTTP, SQLite, restart and replay.

No hosted model, external endpoint, demonstration answer or substitute inference.
This is an independently runnable *localhost* application qualification, not the
protected multi-service backend or an Android-device release certification.
The executable/model are loaded with existing SHA and GGUF custody checks.
Only nonsecret model hashes and measured acceptance results are reported.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
import threading
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.app.local_ai import DurableOfflineAISession, LocalDesktopModel, load_gguf_deployment
from skeleton.app.offline_http import LocalOnlyHTTPServer, OfflineHTTPApplication
from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError

_SCHEMA = "skeleton.jeeves.local-live-acceptance.v1"
_MAX_HTTP_BYTES = 16 * 1024 * 1024


class LiveJeevesFailure(RuntimeError):
    """A bounded local model or durability acceptance failed closed."""


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _request(port: int, token: str, method: str, path: str,
             body: dict[str, Any] | None = None, *,
             allowed_error_status: int | None = None) -> tuple[int, dict[str, Any]]:
    payload = None if body is None else json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    connection = HTTPConnection("127.0.0.1", port, timeout=12)
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        if response.getheader("Content-Length", "").isdigit() and int(
            response.getheader("Content-Length")
        ) > _MAX_HTTP_BYTES:
            raise LiveJeevesFailure("localhost service returned an overlarge response")
        raw = response.read(_MAX_HTTP_BYTES + 1)
        status = response.status
    except (OSError, TimeoutError):
        raise LiveJeevesFailure("local inference service did not respond on loopback") from None
    finally:
        connection.close()
    if len(raw) > _MAX_HTTP_BYTES:
        raise LiveJeevesFailure("local inference response exceeded its bound")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise LiveJeevesFailure("localhost inference returned an invalid JSON body") from None
    if not isinstance(result, dict):
        raise LiveJeevesFailure("localhost inference returned a nonobject response")
    if status >= 400 and status != allowed_error_status:
        raise LiveJeevesFailure("local model request was rejected by the real loopback service")
    return status, result


class _LiveServer:
    """One bounded localhost server epoch with owner-controlled close ordering."""

    def __init__(self, backend: LocalDesktopModel, database: Path, token: str) -> None:
        self.app = OfflineHTTPApplication(backend, database, token=token)
        try:
            self.server = LocalOnlyHTTPServer(self.app, port=0)
        except BaseException:
            self.app.close()
            raise
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.05},
                                       name="jeeves-local-qualification", daemon=True)

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, _type, _value, _traceback):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=12)
        if self.worker.is_alive():
            raise LiveJeevesFailure("local qualification listener did not stop")
        self.app.close()

    @property
    def port(self) -> int:
        return self.server.server_port


def _expect_model(port: int, token: str, digest: str) -> dict[str, Any]:
    status, result = _request(port, token, "GET", "/v1/status")
    if (status != 200 or result.get("local_only") is not True
            or result.get("ready") is not True
            or result.get("model_digest") != digest
            or result.get("async_turns") is not True
            or result.get("cancellation") is not True):
        raise LiveJeevesFailure("local-only execution status or model identity is not trustworthy")
    return result


def _send_turn(port: int, token: str, session_id: str, *,
               request_id: str, text: str, max_tokens: int, timeout: int) -> dict[str, Any]:
    path = "/v1/sessions/" + session_id + "/turns"
    started = time.monotonic()
    status, accepted = _request(port, token, "POST", path, {
        "request_id": request_id,
        "message": text,
        "max_output_tokens": max_tokens,
    })
    if status not in (200, 202) or accepted.get("request_id") != request_id:
        raise LiveJeevesFailure("a real local model turn was not admitted")
    turn_path = path + "/" + request_id
    deadline = started + timeout
    last = accepted
    while time.monotonic() < deadline:
        _, last = _request(port, token, "GET", turn_path)
        if last.get("terminal") is True:
            break
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    if last.get("terminal") is not True:
        # Send explicit cancellation. Never resubmit after an uncertain result.
        _request(port, token, "POST", turn_path + "/cancel", {})
        raise LiveJeevesFailure("local model did not reach a bounded terminal result")
    answer = last.get("result")
    if (last.get("state") != "complete" or not isinstance(answer, dict)
            or not isinstance(answer.get("text"), str) or not answer["text"].strip()
            or answer.get("request_id") != request_id
            or type(answer.get("revision")) is not int
            or type(answer.get("output_tokens")) is not int
            or answer["output_tokens"] < 1
            or answer.get("output_digest") != _digest(answer["text"])
            or answer.get("replayed") is not False):
        raise LiveJeevesFailure("real local generation produced no committed, hashed, nonempty answer")
    proof = answer.get("local_execution_receipt")
    if (not isinstance(proof, dict)
            or proof.get("schema") != "skeleton.ai.local-runtime-receipt.v1"
            or proof.get("authority") != "local-runtime-custody-not-independent-attestation"
            or proof.get("model_digest") != answer.get("model_digest")
            or proof.get("output_sha256") != answer["output_digest"]
            or proof.get("revision") != answer["revision"]
            or not isinstance(proof.get("execution_receipt_digest"), str)
            or len(proof["execution_receipt_digest"]) != 64
            or any(c not in "0123456789abcdef" for c in proof["execution_receipt_digest"])):
        raise LiveJeevesFailure("a completed local model output lacks a verified runtime execution receipt")
    elapsed = max(0.000001, time.monotonic() - started)
    return {
        "result": answer,
        "elapsed_seconds": round(elapsed, 3),
        "output_tokens_per_second_observed": round(answer["output_tokens"] / elapsed, 3),
        "output_sha256": answer["output_digest"],
        "local_execution_receipt_sha256": proof["execution_receipt_digest"],
    }


def _assert_transcript(port: int, token: str, session_id: str,
                       *, replies: list[dict[str, Any]]) -> dict[str, Any]:
    status, state = _request(port, token, "GET", "/v1/sessions/" + session_id)
    rows = state.get("messages")
    if (status != 200 or type(state.get("revision")) is not int
            or state["revision"] != len(replies)
            or not isinstance(rows, list) or len(rows) != len(replies) * 2):
        raise LiveJeevesFailure("durable local conversation lost or duplicated turns")
    for index, reply in enumerate(replies):
        saved = rows[index * 2 + 1]
        if (not isinstance(saved, dict) or saved.get("role") != "assistant"
                or saved.get("content") != reply["text"]):
            raise LiveJeevesFailure("local transcript content changed or was not persisted")
    return state


def qualify_jeeves_live_local(
    model: LocalDesktopModel,
    *,
    timeout_seconds: int = 180,
    output_tokens: int = 16,
) -> dict[str, Any]:
    """Production entrypoint: no alias, no alternate model and no fake GGUF."""
    if getattr(model, "model_id", None) != "jeeves":
        raise LiveJeevesFailure("Jeeves must be the real loaded local model identity")
    return _qualify_actual_local_http(
        model, timeout_seconds=timeout_seconds, output_tokens=output_tokens,
    )


def _qualify_actual_local_http(
    model: LocalDesktopModel,
    *,
    timeout_seconds: int = 180,
    output_tokens: int = 16,
) -> dict[str, Any]:
    """Real native generation + SQLite recovery. Also exercises tiny native in CI.

    This internal acceptance helper never changes a model identity. The
    production entrypoint above requires the exact admitted jeeves identity.
    """
    if (type(timeout_seconds) is not int or not 10 <= timeout_seconds <= 600
            or type(output_tokens) is not int or not 1 <= output_tokens <= 64):
        raise LiveJeevesFailure("qualification time/token budgets are invalid")
    digest = getattr(model, "model_digest", None)
    if not isinstance(digest, str) or len(digest) != 64:
        raise LiveJeevesFailure("Jeeves has no stable admitted model digest")
    token = secrets.token_urlsafe(40)
    first_request_id = "jeeves-qual-" + secrets.token_hex(12)
    second_request_id = "jeeves-qual-" + secrets.token_hex(12)
    second_prompt = (
        "Continue the local Jeeves conversation in one sentence without any cloud model."
    )
    # The same second request ID is first tested against a busy peer and
    # subsequently used for genuine execution after the original server
    # restarts. Denial must not reserve a durable request ID or generate text.
    with TemporaryDirectory(prefix="jeeves-local-http-") as root:
        database = Path(root) / "jeeves.sqlite3"
        with _LiveServer(model, database, token) as instance:
            observed = _expect_model(instance.port, token, digest)
            status, created = _request(instance.port, token, "POST", "/v1/sessions", {})
            session_id = created.get("session_id")
            if status != 201 or not isinstance(session_id, str) or not session_id:
                raise LiveJeevesFailure("local SQLite conversation creation failed")
            first = _send_turn(
                instance.port, token, session_id,
                request_id=first_request_id,
                text="Jeeves local inference test: say one short sentence about offline computing.",
                max_tokens=output_tokens, timeout=timeout_seconds,
            )
            if first["result"].get("model_digest") != digest:
                raise LiveJeevesFailure("Jeeves model identity changed during live inference")
            _assert_transcript(instance.port, token, session_id, replies=[first["result"]])
            # Negative controls execute against the actual local service,
            # not a mocked HTTP adapter. An absent/invalid bearer credential
            # must never disclose model or conversation state.
            status, denied = _request(
                instance.port, ("A" if token[0] != "A" else "B") + token[1:],
                "GET", "/v1/status",
                allowed_error_status=401,
            )
            if status != 401 or not isinstance(denied.get("error"), str):
                raise LiveJeevesFailure("local model service admitted an unauthenticated query")
            # Reusing a committed request ID with different prompt bytes must
            # be denied without generation or a second durable revision. This
            # is a real inference-host check of the idempotency/custody fence.
            status, denied = _request(
                instance.port, token, "POST",
                "/v1/sessions/" + session_id + "/turns",
                {
                    "request_id": first_request_id,
                    "message": "Do not replace the first committed local answer.",
                    "max_output_tokens": output_tokens,
                },
                allowed_error_status=409,
            )
            if status != 409 or not isinstance(denied.get("error"), str):
                raise LiveJeevesFailure("committed local request identity was mutable")
            _assert_transcript(instance.port, token, session_id, replies=[first["result"]])

            # Exercise two independently authenticated LOCAL HTTP applications
            # sharing one private SQLite workspace. While the first holds its
            # operating-system lease, the other must reject a NEW model turn
            # with HTTP 423, never answer from a second backend, and leave the
            # original saved conversation untouched. No mock responses or
            # external inference service are involved.
            peer_token = secrets.token_urlsafe(40)
            with _LiveServer(model, database, peer_token) as peer:
                _expect_model(peer.port, peer_token, digest)
                with instance.app._inference_lease.hold():
                    denied_status, busy = _request(
                        peer.port, peer_token, "POST",
                        "/v1/sessions/" + session_id + "/turn",
                        {
                            "request_id": second_request_id,
                            "message": second_prompt,
                            "max_output_tokens": output_tokens,
                        },
                        allowed_error_status=423,
                    )
                    if (denied_status != 423 or not isinstance(busy.get("error"), str)
                            or busy.get("text") is not None
                            or busy.get("result") is not None):
                        raise LiveJeevesFailure(
                            "a second localhost service bypassed the exclusive native inference lease"
                        )
                    _assert_transcript(
                        peer.port, peer_token, session_id, replies=[first["result"]],
                    )
                _assert_transcript(
                    peer.port, peer_token, session_id, replies=[first["result"]],
                )

        # Fully close the socket, worker, and SQLite handle. A fresh app
        # instance must reconstruct the same source-bound conversation.
        with _LiveServer(model, database, token) as restarted:
            _expect_model(restarted.port, token, digest)
            status, recovered = _request(
                restarted.port, token, "GET",
                "/v1/sessions/" + session_id + "/turns/" + first_request_id,
            )
            historical = recovered.get("result")
            if (status != 200 or recovered.get("state") != "complete"
                    or recovered.get("recovered_from_store") is not True
                    or not isinstance(historical, dict)
                    or historical.get("output_digest") != first["output_sha256"]
                    or historical.get("text") != first["result"]["text"]
                    or not isinstance(historical.get("local_execution_receipt"), dict)
                    or historical["local_execution_receipt"].get("execution_receipt_digest")
                       != first["local_execution_receipt_sha256"]):
                raise LiveJeevesFailure("saved local turn could not be recovered after process restart")
            # A second completed response alone proves no context continuity:
            # a truncated or reset session could have generated it. Independently
            # re-open the canonical SQLite authority and verify the deterministic
            # model request will retain the complete previous user+assistant turn
            # within the current admitted tokenizer/context budget.
            expected_history = (
                ("user", "Jeeves local inference test: say one short sentence about offline computing."),
                ("assistant", first["result"]["text"]),
            )
            preflight = DurableOfflineAISession(
                model, database=database, session_id=session_id,
            )
            try:
                if preflight.history != expected_history:
                    raise LiveJeevesFailure(
                        "the restarted conversation does not retain its exact model-bound turn"
                    )
                prepared, retained_history = preflight._request(
                    second_prompt, output_tokens,
                )
                if (retained_history != expected_history
                        or prepared.history != expected_history
                        or prepared.prompt != second_prompt):
                    raise LiveJeevesFailure(
                        "the continued model request would discard the prior conversation context"
                    )
            finally:
                preflight.close()
            second = _send_turn(
                restarted.port, token, session_id,
                request_id=second_request_id,
                text=second_prompt,
                max_tokens=output_tokens, timeout=timeout_seconds,
            )
            if second["result"].get("model_digest") != digest:
                raise LiveJeevesFailure("Jeeves model identity changed on restarted generation")
            _assert_transcript(
                restarted.port, token, session_id,
                replies=[first["result"], second["result"]],
            )
            # Historical GET proves the persisted result without issuing a
            # second model generation or reusing the POST idempotency key.
            _, same = _request(
                restarted.port, token, "GET",
                "/v1/sessions/" + session_id + "/turns/" + first_request_id,
            )
            if (same.get("result", {}).get("output_digest") != first["output_sha256"]
                    or same.get("result", {}).get("local_execution_receipt", {}).get(
                        "execution_receipt_digest") != first["local_execution_receipt_sha256"]):
                raise LiveJeevesFailure("read-only historical replay no longer matches local execution custody")
    return {
        "schema_version": _SCHEMA, "qualified": True,
        "model_id": model.model_id, "model_digest": digest,
        "local_only": True, "hosted_provider_used": False,
        "transport": "authenticated-loopback-http",
        "storage": "local-sqlite-reopened",
        "actual_model_turns": 2,
        "durable_recovery_verified": True, "read_only_replay_verified": True,
        "context_continuation_verified": True,
        "context_preflight_history_retained": True,
        "context_preflight_is_generation_proof": False,
        "run_1_output_sha256": first["output_sha256"],
        "run_2_output_sha256": second["output_sha256"],
        "run_1_execution_receipt_sha256": first["local_execution_receipt_sha256"],
        "run_2_execution_receipt_sha256": second["local_execution_receipt_sha256"],
        "runtime_receipts_survived_restart": True,
        "unauthenticated_local_query_denied": True,
        "committed_request_rewrite_denied": True,
        "competing_local_service_inference_denied": True,
        "denied_peer_request_committed_after_restart": True,
        "turn_metrics": [
            {"elapsed_seconds": t["elapsed_seconds"],
             "observed_output_tokens_per_second": t["output_tokens_per_second_observed"],
             "actual_output_tokens": t["result"]["output_tokens"]}
            for t in (first, second)
        ],
        "adaptive_metal_launch": observed.get("adaptive_metal_launch"),
        "protected_backend_verified": False,
        "mobile_device_verified": False,
        "underlying_model_quality_certified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="existing SHA-pinned local model and llama.cpp executable with model_id=jeeves")
    parser.add_argument("--timeout", type=int, default=180, help="per-turn 10–600 seconds")
    parser.add_argument("--output-tokens", type=int, default=16, help="per-turn 1–64 generation tokens")
    args = parser.parse_args(argv)
    try:
        pinned = LocalModelDeployment.load(args.manifest)
        if pinned.model_id != "jeeves" or pinned.runtime_kind != "llama.cpp-cli":
            raise LiveJeevesFailure("only the pinned local Jeeves GGUF model can be qualified")
        model = load_gguf_deployment(args.manifest)
        proof = qualify_jeeves_live_local(
            model, timeout_seconds=args.timeout, output_tokens=args.output_tokens,
        )
        if proof["model_digest"] != pinned.model_sha256:
            raise LiveJeevesFailure("live local model did not match GGUF digest pin")
        print(json.dumps(proof, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, RuntimeContractError, TimeoutError):
        # Do not expose private path or model output in failure messages.
        print(json.dumps({"qualified": False, "error": "Local model, HTTP or durable inference qualification failed; inspect private host diagnostics."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
