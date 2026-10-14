import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from skeleton.security.activation_security import (
    SECURITY_GATES,
    run_bot_activation_security_baseline,
)


class TestActivationSecurityTimeouts(unittest.TestCase):
    def test_only_full_secret_scan_gets_extended_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for relative in SECURITY_GATES:
                path=root/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text("pass\n",encoding="utf-8")

            observed=[]
            def fake_run(*args, **kwargs):
                observed.append((Path(args[0][1]).name, kwargs["timeout"]))
                return SimpleNamespace(returncode=0)

            with patch("skeleton.security.activation_security.subprocess.run", side_effect=fake_run):
                run_bot_activation_security_baseline(repo_root=root, env={})

        timeouts=dict(observed)
        self.assertEqual(timeouts["check_secret_hygiene.py"],180)
        for name, timeout in observed:
            if name != "check_secret_hygiene.py":
                self.assertEqual(timeout,90)


if __name__=="__main__":
    unittest.main()
