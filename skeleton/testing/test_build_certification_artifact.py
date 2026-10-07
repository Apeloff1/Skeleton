import json
from skeleton.automation.build_certification_artifact import render
from skeleton.automation.build_certificate import BuildCertificate
from skeleton.automation.build_completion_proof import CompletionProof
def test_artifact_contains_both_digests():
 c=BuildCertificate("id","a"*40,"b"*40,1,1,("c"*64,),"complete");p=CompletionProof("b"*40,"d"*64,"e"*64,"f"*64,"1"*64,("2"*64,));x=json.loads(render(c,p));assert len(x["certificate_sha256"])==64 and len(x["proof_sha256"])==64
