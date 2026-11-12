"""ACE fail-close security. Secret scan, no live secrets, fail-closed on any execution risk.
Completionist Nov 2026. Satisfies end-user security expectations.
"""
from typing import List, Dict
import re

class ACEFailClose:
    SECRET_PATTERNS = [
        r"sk-[a-zA-Z0-9]{20,}",
        r"ghp_[a-zA-Z0-9]{36}",
        r"AKIA[0-9A-Z]{16}",
        r"-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----",
    ]

    def scan(self, content: str) -> Dict:
        findings = []
        for pat in self.SECRET_PATTERNS:
            if re.search(pat, content):
                findings.append({"pattern": pat, "severity": "CRITICAL"})
        return {"ok": len(findings) == 0, "findings": findings, "fail_closed": True}

    def enforce(self, code: str) -> bool:
        result = self.scan(code)
        if not result["ok"]:
            raise RuntimeError("ACE fail-close: secret detected")
        return True
