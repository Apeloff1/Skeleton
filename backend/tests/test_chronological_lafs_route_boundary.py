"""Private LAFS retrieval must select a declared local runtime."""
import asyncio
import base64

import pytest
from fastapi import HTTPException
from routes import lafs as routes


def test_explicit_local_selection_never_chooses_external_fallback():
    catalog = {"models": [
        {"provider_id": "cloud", "model_id": "remote", "selectable": True, "active": True, "execution_mode": "remote"},
        {"provider_id": "native", "model_id": "local", "selectable": True, "active": False, "execution_mode": "local"},
    ]}
    assert routes._local_pair(catalog) == ("native", "local")
    assert routes._local_pair({"models": catalog["models"][:1]}) is None


def test_pdf_uses_shared_isolated_decoder(monkeypatch):
    async def extract(payload, mime):
        assert payload == b"%PDF-example"
        assert mime == "application/pdf"
        return {"text": "untrusted text"}
    monkeypatch.setattr(routes, "extract_ephemeral_attachment", extract)
    assert asyncio.run(routes._pdf_evidence(base64.b64encode(b"%PDF-example").decode())) == "untrusted text"
    with pytest.raises(HTTPException):
        asyncio.run(routes._pdf_evidence("invalid base64"))


def test_deployed_shared_cabinet_requires_specific_operator(monkeypatch):
    monkeypatch.setattr(routes, "auth_enforced", lambda: True)
    monkeypatch.setenv("LAFS_OPERATOR_TENANT", "tenant-a")
    monkeypatch.setenv("LAFS_OPERATOR_ID", "operator@example.invalid")
    operator = {"tenant_id": "tenant-a", "email": "operator@example.invalid", "role": "admin"}
    assert routes._admin(operator) == operator
    with pytest.raises(HTTPException) as error:
        routes._admin({**operator, "tenant_id": "tenant-b"})
    assert error.value.status_code == 403
