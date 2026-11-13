"""Deterministic corpus integrity census, not third-party proof of source authenticity."""
from __future__ import annotations
import hashlib
from importlib import resources
from .contracts import fail,strict_json
from .catalog import domains

def inventory():
    root=resources.files(__package__)
    digest=hashlib.sha256();count=0;cases=0
    for name in domains():
        items=[(f"schemas/{name}.json",root.joinpath("schemas",name+".json")),
               (f"policies/{name}.py",root.joinpath("policies",name+".py")),
               (f"bindings/{name}.py",root.joinpath("bindings",name+".py")),
               (f"states/{name}.py",root.joinpath("states",name+".py")),
               (f"guides/{name}.md",root.joinpath("guides",name+".md"))]
        case_files=sorted(f for f in root.joinpath("cases",name).iterdir()
                          if f.name.endswith(".json"))
        if len(case_files)!=22:fail("expected exactly 22 source cases for domain")
        items.extend((f"cases/{name}/{f.name}",f) for f in case_files)
        allowed=denied=0
        for path,file in items:
            if not file.is_file() or file.is_symlink():
                fail("missing or symlinked assurance source")
            blob=file.read_bytes()
            if not 1<=len(blob)<=131072:fail("source bound exceeded")
            if path.startswith("cases/"):
                case=strict_json(blob,maximum=131072)
                if type(case) is not dict or case.get("domain")!=name:
                    fail("source case domain mismatch")
                if case.get("release_claim") is not False:
                    fail("source fixture cannot claim external release")
                if case.get("expected")=="accept":allowed+=1
                elif case.get("expected")=="reject":denied+=1
                else:fail("ambiguous adversarial expectation")
                cases+=1
            encoded=path.encode("utf-8")
            digest.update(len(encoded).to_bytes(4,"big"))
            digest.update(encoded)
            digest.update(len(blob).to_bytes(8,"big"))
            digest.update(blob)
            count+=1
        if (allowed,denied)!=(2,20):
            fail("insufficient boundary-specific denials")
    if count!=1080 or cases!=880:fail("incomplete registry inventory")
    return {"schema":"ai-reliability-source-inventory.v1","domains":40,
            "source_files":count,"cases":cases,"expected_accepts":80,
            "expected_denials":800,"sha256":digest.hexdigest(),
            "native_model_tested":False,"release_certified":False}
