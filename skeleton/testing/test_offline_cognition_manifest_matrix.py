"""Run 256 original hostile manifest-custody source scenarios.

Each case is an independently checked, source-controlled negative input. The
test never invokes installed GGUF weights or claims device/rights qualification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    CognitionError,Scope,canonical,loads,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    verify_signed_manifest,sign_manifest_for_operator,ingest_authorized_sources,
)

HERE=Path(__file__).resolve().parent/"fixtures"/"offline_source_manifest"
KEY=bytes(range(32))
SCOPE=Scope("local","owner","a"*64,"b"*64)
RAW=b"Deterministic operator-approved exact original source bytes"
RIGHTS="d"*64
KINDS=frozenset(("digest_swap","identity_swap","path_traversal","hmac_flip"))
STABLE_FIELDS=frozenset((
    "schema","id","attack","expected","payload","trust_boundary",
    "precondition","attacker_control","evaluation_phase",
    "expected_observations","recovery_policy","source_evidence_type",
    "independent_model_execution_proved","independent_windows_device_proved",
))
FALSE_ASSERTIONS=frozenset((
    "source_data_exfiltrated","foreign_tenant_admitted",
    "unauthorized_native_dispatch","automatic_retry",
    "approved_rights_fabricated","release_certified",
))

def _canonical_record():
    return {
        "schema":"offline-signed-source-manifest.v1",
        "tenant":SCOPE.tenant,"subject":SCOPE.subject,
        "model_sha256":SCOPE.model_sha256,
        "tokenizer_sha256":SCOPE.tokenizer_sha256,
        "issued_at":100,"expires_at":200,
        "nonce":"f"*32,
        "sources":[{
            "source_id":"document","filename":"source.txt",
            "sha256":hashlib.sha256(RAW).hexdigest(),
            "rights_receipt_sha256":RIGHTS,"approved":True,
        }],
    }

def _cases():
    if HERE.is_symlink() or not HERE.is_dir():
        raise CognitionError("manifest source corpus unavailable or linked")
    paths=sorted(x for x in HERE.iterdir() if x.suffix==".json")
    if len(paths)!=256:
        raise CognitionError("all 256 hostile signed-manifest cases required")
    loaded=[];seen=set()
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise CognitionError("unsafe signed-manifest source case")
        case=loads(path.read_bytes(),maximum=16384)
        if (type(case) is not dict or set(case)!=STABLE_FIELDS or
            case.get("schema")!="offline-source-manifest-negative-case.v1" or
            case.get("id")!=path.stem or
            case["id"] in seen or case["attack"] not in KINDS or
            case["expected"]!="reject" or
            case["independent_model_execution_proved"] is not False or
            case["independent_windows_device_proved"] is not False):
            raise CognitionError("untrusted or duplicate hostile manifest case")
        if (type(case["expected_observations"]) is not dict or
            set(case["expected_observations"])!=FALSE_ASSERTIONS or
            any(value is not False for value in case["expected_observations"].values())):
            raise CognitionError("false release assertion in manifest casebook")
        seen.add(case["id"]);loaded.append(case)
    for kind in KINDS:
        if sum(x["attack"]==kind for x in loaded)!=64:
            raise CognitionError("source attack family incomplete")
    return tuple(loaded)


class SignedSourceManifestMatrixTests(unittest.TestCase):
    def test_exact_negative_matrix_denies_every_attack(self):
        cases=_cases()
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/"sources"
            directory.mkdir(mode=0o700)
            file=directory/"source.txt"
            file.write_bytes(RAW)
            file.chmod(0o600)
            for case in cases:
                with self.subTest(case=case["id"]):
                    self._check(case,directory)

    def _check(self,case,directory):
        r=_canonical_record()
        kind=case["attack"]
        if kind=="digest_swap":
            value=case["payload"]
            self.assertIs(type(value),str)
            self.assertEqual(len(value),64)
            r["sources"][0]["sha256"]=value
            signed=sign_manifest_for_operator(r,KEY)
            verified=verify_signed_manifest(signed,KEY,observed_at=150)
            with self.assertRaises(CognitionError):
                ingest_authorized_sources(directory,verified,scope=SCOPE,observed_at=150)
        elif kind=="identity_swap":
            value=case["payload"]
            self.assertIs(type(value),str)
            r["subject"]=value
            signed=sign_manifest_for_operator(r,KEY)
            verified=verify_signed_manifest(signed,KEY,observed_at=150)
            self.assertNotEqual(verified.scope,SCOPE)
            with self.assertRaises(CognitionError):
                ingest_authorized_sources(directory,verified,scope=SCOPE,observed_at=150)
        elif kind=="path_traversal":
            value=case["payload"]
            self.assertIs(type(value),str)
            r["sources"][0]["filename"]=value
            with self.assertRaises(CognitionError):
                verify_signed_manifest(sign_manifest_for_operator(r,KEY),
                                       KEY,observed_at=150)
        elif kind=="hmac_flip":
            pos=case["payload"]
            self.assertIs(type(pos),int)
            self.assertTrue(0<=pos<64)
            raw=sign_manifest_for_operator(r,KEY)
            envelope=json.loads(raw)
            old=envelope["mac"]
            other="0" if old[pos]!="0" else "1"
            envelope["mac"]=old[:pos]+other+old[pos+1:]
            with self.assertRaises(CognitionError):
                verify_signed_manifest(canonical(envelope),KEY,observed_at=150)
        else:
            self.fail("unknown source custody threat")

    def test_matrix_is_original_and_bounded(self):
        cases=_cases()
        self.assertEqual(len(cases),256)
        self.assertEqual(len({x["id"] for x in cases}),256)
        self.assertEqual(set(x["attack"] for x in cases),KINDS)


if __name__=="__main__":
    unittest.main()
