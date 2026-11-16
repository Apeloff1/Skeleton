"""Actual loopback TLS and independent policy protocol qualification.

Keys and CA are ephemeral fixtures, not production signer or device evidence.
No live application conversation or real credentials are used.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import ssl
import threading
import time
from uuid import uuid4

import httpx
import pytest
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from scripts.independent_reviewer_policy import (
    ATTEST_SCHEMA, POLICY_SCHEMA, REVIEW_SCHEMA, PolicyDenied,
    ReviewerPolicySigner, ReviewPolicy, canonical, load_signer,
)
from scripts.serve_independent_reviewer import BoundedTLSReviewer, server_tls
from skeleton.ai.runtime.inference.reviewer_custody import (
    ReviewerCustodyError, ReviewerCustodyVerifier, ReviewerTrustAnchor,
)
from skeleton.ai.runtime.inference.signed_reviewer_client import SignedReviewerClient, canonical_verdict

TEXT = "independently reviewed corpus fixture"
SCOPE = dict(tenant_id="tenant", actor_id="actor", context_id="thread",
             model_digest="a"*64, runtime_digest="b"*64, tokenizer_digest="c"*64)
CLIENT = "d"*64


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def policy(client=CLIENT, **updates):
    now = int(time.time())
    doc = dict(schema=POLICY_SCHEMA, authority_id="reviewer", deployment_domain="separate-domain",
               issued_at=now-1, expires_at=now+600, client_certificates=[client],
               approved_contexts=[digest(TEXT.encode())], challenge_scopes=[SCOPE])
    doc.update(updates)
    raw = canonical(doc)
    return ReviewPolicy.parse(raw, digest(raw))


def review(text=TEXT, nonce=None):
    return canonical(dict(schema=REVIEW_SCHEMA, nonce=nonce or uuid4().hex + "0"*16,
                          context_sha256=digest(text.encode()), untrusted_text=text))


def challenge(**changes):
    values = dict(schema=ATTEST_SCHEMA, nonce=uuid4().hex + "1"*16,
                  authority_id="reviewer", deployment_domain="separate-domain", epoch=2, **SCOPE)
    values.update(changes)
    return canonical(values)


def test_exact_policy_pins_and_signature_wire_compatibility():
    key = Ed25519PrivateKey.generate()
    s = ReviewerPolicySigner(policy(), key)
    for text, allowed in ((TEXT, True), (TEXT+" ", False), ("unknown", False)):
        verdict = json.loads(s.review(review(text), CLIENT))
        signature = base64.b64decode(verdict.pop("signature"), validate=True)
        key.public_key().verify(signature, canonical_verdict(verdict))
        assert verdict["allowed"] is allowed
        assert verdict["context_sha256"] == digest(text.encode())
    with pytest.raises(PolicyDenied):
        s.review(review(TEXT), "0"*64)
    raw = challenge()
    key.public_key().verify(s.attest(raw, CLIENT), raw)
    with pytest.raises(PolicyDenied):
        s.attest(raw, CLIENT)
    for changed in (dict(actor_id="other"), dict(tenant_id="other"), dict(epoch=True),
                    dict(epoch=3), dict(runtime_digest="0"*64), dict(deployment_domain="other")):
        with pytest.raises(PolicyDenied):
            s.attest(challenge(**changed), CLIENT)
    with pytest.raises(PolicyDenied):
        s.attest(b"arbitrary signed content", CLIENT)


def test_nonce_shared_and_exhaustion_denies_instead_of_eviction():
    key = Ed25519PrivateKey.generate()
    s = ReviewerPolicySigner(policy(), key, replay_limit=2)
    nonce = "1"*48
    s.review(review(nonce=nonce), CLIENT)
    with pytest.raises(PolicyDenied):
        s.attest(challenge(nonce=nonce), CLIENT)
    s.attest(challenge(), CLIENT)
    with pytest.raises(PolicyDenied):
        s.review(review(), CLIENT)


def test_expired_policy_and_duplicate_or_noncanonical_request_denial():
    p = policy()
    s = ReviewerPolicySigner(p, Ed25519PrivateKey.generate(), clock=lambda: p.expires_at)
    with pytest.raises(PolicyDenied):
        s.review(review(), CLIENT)
    s = ReviewerPolicySigner(p, Ed25519PrivateKey.generate())
    with pytest.raises(PolicyDenied):
        s.review(review()[:-1]+b',"nonce":"'+b"0"*48+b'"}', CLIENT)
    with pytest.raises(PolicyDenied):
        s.attest(challenge()+b"\n", CLIENT)
    with pytest.raises(PolicyDenied):
        ReviewPolicy.parse(b"{}", "0"*64)
    with pytest.raises(PolicyDenied):
        policy(approved_contexts=[digest(TEXT.encode())]*2)


def test_raw_signer_key_requires_owner_only_regular_file(tmp_path):
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    path = tmp_path / "signing.raw"
    path.write_bytes(raw)
    path.chmod(0o600)
    payload = b"fixture"
    key.public_key().verify(load_signer(path).sign(payload), payload)
    path.chmod(0o644)
    with pytest.raises(PolicyDenied):
        load_signer(path)
    path.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(path)
    with pytest.raises((PolicyDenied, OSError)):
        load_signer(alias)


def _certificates(base):
    now = datetime.now(timezone.utc)
    ca_key = generate_private_key(SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture-ca")])
    def builder(subject, key):
        return (x509.CertificateBuilder().subject_name(subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-timedelta(minutes=2)).not_valid_after(now+timedelta(minutes=20)))
    ca = (builder(ca_name, ca_key).issuer_name(ca_name)
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    ca_path = base / "ca.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    def leaf(name, server=False):
        key = generate_private_key(SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        b = (builder(subject, key).issuer_name(ca_name)
             .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
             .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if server
                                                    else ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False))
        if server:
            b = b.add_extension(x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        cert = b.sign(ca_key, hashes.SHA256())
        certpath, keypath = base / (name+".pem"), base / (name+".key")
        certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        keypath.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        keypath.chmod(0o600)
        return certpath, keypath, digest(cert.public_bytes(serialization.Encoding.DER))
    return ca_path, leaf("server", True), leaf("allowed"), leaf("foreign")


def client_tls(ca, leaf=None):
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_verify_locations(cafile=str(ca))
    if leaf is not None:
        tls.load_cert_chain(certfile=str(leaf[0]), keyfile=str(leaf[1]))
    return tls


@contextmanager
def running_reviewer(tmp_path):
    ca, cert, client, foreign = _certificates(tmp_path)
    key = Ed25519PrivateKey.generate()
    p = policy(client[2])
    signer = ReviewerPolicySigner(p, key)
    tls = server_tls(cert=cert[0], key=cert[1], client_ca=ca)
    endpoint = BoundedTLSReviewer(("127.0.0.1", 0), signer=signer, tls=tls)
    thread = threading.Thread(target=endpoint.serve_forever, kwargs={"poll_interval":.05})
    thread.start()
    anchor = ReviewerTrustAnchor(p.authority_id, p.deployment_domain,
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    try:
        yield f"https://127.0.0.1:{endpoint.server_port}", anchor, ca, client, foreign
    finally:
        endpoint.shutdown()
        thread.join(timeout=5)
        endpoint.server_close()
        assert not thread.is_alive()


def test_real_mutual_tls_signed_review_and_attestation(tmp_path):
    with running_reviewer(tmp_path) as (url, anchor, ca, leaf, foreign):
        async def scenario():
            client = SignedReviewerClient(base_url=url, trust_anchor=anchor,
                                            tls_context=client_tls(ca, leaf))
            try:
                assert client(TEXT, digest(TEXT.encode())).allowed is True
                assert client("unknown", digest(b"unknown")).allowed is False
                verifier = ReviewerCustodyVerifier(reviewer=client,
                    authority_id=anchor.authority_id, trust_anchor=anchor)
                await verifier.verify(**SCOPE, epoch=2)
                with pytest.raises(ReviewerCustodyError):
                    await verifier.verify(**{**SCOPE, "actor_id":"foreign"}, epoch=2)
                with pytest.raises(ReviewerCustodyError):
                    await client.attest_challenge(b"unbound arbitrary payload")
            finally:
                await client.aclose()
            for unauthorized in (None, foreign):
                other = SignedReviewerClient(base_url=url, trust_anchor=anchor,
                                              tls_context=client_tls(ca, unauthorized))
                try:
                    with pytest.raises(ReviewerCustodyError):
                        other(TEXT, digest(TEXT.encode()))
                finally:
                    await other.aclose()
        asyncio.run(scenario())


def test_live_http_wire_denies_replay_duplicate_headers_and_unknown_paths(tmp_path):
    with running_reviewer(tmp_path) as (url, _, ca, leaf, _):
        with httpx.Client(verify=client_tls(ca, leaf), trust_env=False,
                          follow_redirects=False, timeout=3) as client:
            body = review()
            good = client.post(url+"/v1/review", content=body,
                               headers={"Content-Type":"application/json"})
            assert good.status_code == 200
            assert client.post(url+"/v1/review", content=body,
                               headers={"Content-Type":"application/json"}).status_code == 403
            assert client.post(url+"/v1/unknown", content=b"x").status_code == 404
            assert client.post(url+"/v1/review", content=review(),
                headers=[("Content-Type","application/json"),("Content-Type","application/json")]).status_code == 403
