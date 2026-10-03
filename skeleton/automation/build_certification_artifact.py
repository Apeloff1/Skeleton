"""Canonical final artifact containing certificate and completion proof."""
from __future__ import annotations
import json
from dataclasses import asdict
from .build_certificate import BuildCertificate
from .build_completion_proof import CompletionProof
def render(certificate:BuildCertificate,proof:CompletionProof)->str:
 certificate.validate();proof.validate()
 return json.dumps({"schema":"autonomous-studio.certified-build.v1","certificate":asdict(certificate),"certificate_sha256":certificate.digest(),"proof":asdict(proof),"proof_sha256":proof.digest()},sort_keys=True,indent=2)+"\n"
