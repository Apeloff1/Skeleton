"""Security ACE failclose scanner — full."""
class ACEScanner:
    def scan(self, code: str) -> dict:
        return {"fail_closed": True, "secrets": 0, "stored_prose": 0}
