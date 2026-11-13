"""Offline desktop subprocess: no inherited provider, proxy or shell authority.

All cases are source-only. A synthetic Popen never starts GGUF or an OS child.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.laptop_runtime import desktop_client
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_environment import (
    NativeChildEnvironmentHold,
    native_child_environment,
)


class NativeEnvironmentContractTests(unittest.TestCase):
    def test_known_cloud_keys_and_proxies_do_not_cross_native_process_boundary(self):
        source = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/local-operator",
            "CUDA_VISIBLE_DEVICES": "0,1",
            "OPENAI_API_KEY": "secret-openai",
            "ANTHROPIC_API_KEY": "secret-anthropic",
            "HF_TOKEN": "secret-huggingface",
            "GITHUB_TOKEN": "secret-github",
            "AWS_SECRET_ACCESS_KEY": "secret-aws",
            "HTTP_PROXY": "http://proxy.invalid",
            "HTTPS_PROXY": "http://proxy.invalid",
            "ALL_PROXY": "socks5://proxy.invalid",
            "NO_PROXY": "localhost",
            "PYTHONPATH": "/tmp/untrusted-imports",
            "PYTHONHOME": "/tmp/untrusted-python",
            "LD_PRELOAD": "/tmp/untrusted.so",
            "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
            "BASH_ENV": "/tmp/untrusted-shell-hook",
        }
        before = dict(source)
        result = native_child_environment(source)
        self.assertEqual(result, {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/local-operator",
            "CUDA_VISIBLE_DEVICES": "0,1",
        })
        self.assertEqual(source, before)
        self.assertNotIn("secret-openai", repr(result))

    def test_windows_and_gpu_essentials_survive_without_exposing_secrets(self):
        source = {
            "Path": "C:\\Windows\\System32;C:\\Python",
            "SystemRoot": "C:\\Windows",
            "WINDIR": "C:\\Windows",
            "TEMP": "C:\\Users\\Owner\\AppData\\Local\\Temp",
            "PATHEXT": ".COM;.EXE",
            "USERPROFILE": "C:\\Users\\Owner",
            "VIRTUAL_ENV": "C:\\Users\\Owner\\venv",
            "CUDA_PATH": "C:\\Program Files\\CUDA",
            "NVIDIA_VISIBLE_DEVICES": "all",
            "MKL_NUM_THREADS": "4",
            "CUSTOM_CLOUD_TOKEN": "secret",
        }
        result = native_child_environment(source)
        for key in source:
            if key != "CUSTOM_CLOUD_TOKEN":
                self.assertEqual(result[key], source[key])
        self.assertNotIn("CUSTOM_CLOUD_TOKEN", result)

    def test_empty_environment_is_explicit_and_not_a_proxy_fallback(self):
        self.assertEqual(native_child_environment({}), {})

    def test_non_mapping_environment_rejected(self):
        for value in ([], "PATH=/bin", 17, True):
            with self.subTest(value=value):
                with self.assertRaises(NativeChildEnvironmentHold):
                    native_child_environment(value)

    def test_non_string_allowed_env_values_rejected(self):
        with self.assertRaises(NativeChildEnvironmentHold):
            native_child_environment({"PATH": None})

    def test_control_characters_fail_before_child_is_spawned(self):
        for value in ("/usr/bin\x00bad", "/usr/bin\nnew", "/usr/bin\rnew"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(NativeChildEnvironmentHold):
                    native_child_environment({"PATH": value})

    def test_invalid_unicode_cannot_cross_environment(self):
        with self.assertRaises(NativeChildEnvironmentHold):
            native_child_environment({"HOME": "\ud800"})

    def test_per_value_budget_rejected(self):
        with self.assertRaises(NativeChildEnvironmentHold):
            native_child_environment({"PATH": "x" * 32769})

    def test_aggregate_environment_budget_rejected(self):
        from skeleton.ai.runtime.operational_ai.laptop_runtime import desktop_environment
        large = {key: "x" * 4000 for key in desktop_environment._ALLOWED}
        self.assertGreater(len(large), 33)
        with self.assertRaises(NativeChildEnvironmentHold):
            native_child_environment(large)

    def test_bridge_passes_filtered_map_to_popen_and_never_starts_real_child(self):
        seen = []
        process_instances = []

        class FakeProcess:
            def __init__(self):
                self.stdin = io.BytesIO()
                self.stdout = io.BytesIO(b"{}")
                self.alive = True
            def poll(self):
                return None if self.alive else 0
            def terminate(self):
                self.alive = False
            def wait(self, timeout=None):
                return 0

        def fake_popen(*args, **kwargs):
            seen.append((args, kwargs))
            child = FakeProcess()
            process_instances.append(child)
            return child

        class FakeTimer:
            daemon = False
            def __init__(self, *_args, **_kwargs):
                pass
            def start(self):
                pass
            def cancel(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            config = desktop_client.DesktopConfig(
                model_root=str(Path(tmp) / "models"),
                state_dir=str(Path(tmp) / "state"),
                tenant="local",
                subject="owner",
            )
            bridge = desktop_client.DesktopBridge(config)
            with patch.dict(os.environ, {
                "PATH": "/usr/bin",
                "OPENAI_API_KEY": "should-never-reach-child",
                "HTTP_PROXY": "http://not-allowed.invalid",
            }, clear=True):
                with patch.object(desktop_client.subprocess, "Popen", fake_popen):
                    with patch.object(desktop_client.threading, "Timer", FakeTimer):
                        with patch.object(desktop_client, "read_frame",
                                          return_value={"status": "native-gguf-ready"}):
                            with patch.object(bridge, "_verify", side_effect=lambda value: value):
                                try:
                                    self.assertEqual(bridge.open()["status"], "native-gguf-ready")
                                finally:
                                    bridge.abort()
        self.assertEqual(len(seen), 1)
        env = seen[0][1]["env"]
        self.assertEqual(env.get("PATH"), "/usr/bin")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("HTTP_PROXY", env)
        self.assertFalse(process_instances[0].alive)


if __name__ == "__main__":
    unittest.main()
