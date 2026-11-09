from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api.engine_authority import EngineAuthorityRegistry, EngineServiceGrant
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_service import EngineExecutionService, SQLiteEngineSubmissionStore
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import ProviderImageResponse, ProviderSpeechResponse


_SERVICE_TOKEN = "test-engine-media-token-" + ("x" * 40)


class _FakeAdapter:
    def __init__(self) -> None:
        self.image_requests = []
        self.speech_requests = []
        self.variation_requests = []
        self.edit_requests = []

    async def generate_image(self, request):
        self.image_requests.append(request)
        return ProviderImageResponse(
            images=({"data": "aGVsbG8=", "format": "base64_png"},),
            provider="openai",
            model="gpt-image-1",
            request_id="img-1",
            governance_decision_id="gov-image",
            admission_decision_id="adm-image",
            data_class="internal",
        )

    async def create_image_variation(self, image, **kwargs):
        self.variation_requests.append((image, kwargs))
        return ProviderImageResponse(
            images=({"data": "aGVsbG8=", "format": "base64_png"},),
            provider="openai",
            model="image-variation",
            request_id="var-1",
            governance_decision_id="gov-var",
            admission_decision_id="adm-var",
            data_class="internal",
        )

    async def edit_image(self, image, **kwargs):
        self.edit_requests.append((image, kwargs))
        return ProviderImageResponse(
            images=({"data": "aGVsbG8=", "format": "base64_png"},),
            provider="openai",
            model="image-edit",
            request_id="edit-1",
            governance_decision_id="gov-edit",
            admission_decision_id="adm-edit",
            data_class="internal",
        )

    async def synthesize_speech(self, request):
        self.speech_requests.append(request)
        return ProviderSpeechResponse(
            audio=b"audio-bytes",
            provider="openai",
            model="tts-1-hd",
            response_format="mp3",
            request_id="speech-1",
            governance_decision_id="gov-speech",
            admission_decision_id="adm-speech",
            data_class="internal",
        )


class _FakeRegistry:
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    def require_active(self):
        return self.adapter


def _service(tmp_path, *, scopes=frozenset({"engine:media"}), capabilities=frozenset({"media.image", "media.speech"})):
    authorities = EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal="backend-service",
                scopes=scopes,
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=capabilities,
            )
        ]
    )
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "media-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "media-submission.sqlite3"),
        authorities,
    )


def _client(service, adapter):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: _SERVICE_TOKEN
    app.dependency_overrides[_engine_coordinator] = lambda: SimpleNamespace(
        provider_registry=_FakeRegistry(adapter)
    )
    return TestClient(app)


def _headers():
    return {
        "authorization": "Bearer " + _SERVICE_TOKEN,
        "x-zaibatsu-attester": "backend-service",
    }


def test_engine_media_generate_and_speech_are_authenticated_and_bounded(tmp_path) -> None:
    adapter = _FakeAdapter()
    client = _client(_service(tmp_path), adapter)

    image = client.post(
        "/api/v1/engine/media/images/generate",
        headers=_headers(),
        json={
            "actor_id": "image-route",
            "tenant_id": "tenant-a",
            "operation_id": "img-op",
            "prompt": "draw a deterministic robot",
            "size": "1024x1024",
            "quality": "standard",
            "count": 1,
        },
    )
    assert image.status_code == 200
    assert image.json()["images"][0]["data"] == "aGVsbG8="
    assert adapter.image_requests[0].tenant_id == "tenant-a"
    assert adapter.image_requests[0].operation_id == "img-op"

    speech = client.post(
        "/api/v1/engine/media/speech",
        headers=_headers(),
        json={
            "actor_id": "tts-route",
            "tenant_id": "tenant-a",
            "operation_id": "speech-op",
            "text": "Hello there.",
            "voice": "nova",
            "speed": 1.0,
            "response_format": "mp3",
        },
    )
    assert speech.status_code == 200
    assert speech.json()["audio_base64"] == "YXVkaW8tYnl0ZXM="
    assert adapter.speech_requests[0].tenant_id == "tenant-a"
    assert adapter.speech_requests[0].operation_id == "speech-op"


def test_engine_media_variation_and_edit_decode_binary_only_after_authority(tmp_path) -> None:
    adapter = _FakeAdapter()
    client = _client(_service(tmp_path), adapter)

    variation = client.post(
        "/api/v1/engine/media/images/variation",
        headers=_headers(),
        json={
            "actor_id": "image-route",
            "tenant_id": "tenant-a",
            "operation_id": "var-op",
            "image_base64": "aGVsbG8=",
            "count": 1,
            "size": "1024x1024",
        },
    )
    assert variation.status_code == 200
    assert adapter.variation_requests[0][0] == b"hello"

    edit = client.post(
        "/api/v1/engine/media/images/edit",
        headers=_headers(),
        json={
            "actor_id": "image-route",
            "tenant_id": "tenant-a",
            "operation_id": "edit-op",
            "image_base64": "aGVsbG8=",
            "mask_base64": "bWFzaw==",
            "prompt": "make it blue",
            "size": "1024x1024",
        },
    )
    assert edit.status_code == 200
    assert adapter.edit_requests[0][0] == b"hello"
    assert adapter.edit_requests[0][1]["mask"] == b"mask"


def test_engine_media_scope_and_capability_denial_happen_before_provider_io(tmp_path) -> None:
    adapter = _FakeAdapter()
    no_scope = _client(
        _service(tmp_path, scopes=frozenset({"engine:read"})),
        adapter,
    )
    denied = no_scope.post(
        "/api/v1/engine/media/images/generate",
        headers=_headers(),
        json={
            "actor_id": "image-route",
            "tenant_id": "tenant-a",
            "operation_id": "denied-op",
            "prompt": "do not execute",
        },
    )
    assert denied.status_code == 403
    assert adapter.image_requests == []

    speech_denied = _client(
        _service(
            tmp_path,
            capabilities=frozenset({"media.image"}),
        ),
        adapter,
    ).post(
        "/api/v1/engine/media/speech",
        headers=_headers(),
        json={
            "actor_id": "tts-route",
            "tenant_id": "tenant-a",
            "operation_id": "denied-speech",
            "text": "do not execute",
        },
    )
    assert speech_denied.status_code == 403
    assert adapter.speech_requests == []


def test_engine_media_rejects_bad_base64_before_provider_io(tmp_path) -> None:
    adapter = _FakeAdapter()
    client = _client(_service(tmp_path), adapter)
    response = client.post(
        "/api/v1/engine/media/images/edit",
        headers=_headers(),
        json={
            "actor_id": "image-route",
            "tenant_id": "tenant-a",
            "operation_id": "bad-b64",
            "image_base64": "not***base64",
            "prompt": "edit",
        },
    )
    assert response.status_code == 422
    assert adapter.edit_requests == []
