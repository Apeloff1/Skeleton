from __future__ import annotations

from pathlib import Path

from scripts.check_sast_security import javascript_violations, violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def _scan_js(tmp_path: Path, source: str, suffix: str = ".ts") -> list[str]:
    path = tmp_path / f"sample{suffix}"
    path.write_text(source, encoding="utf-8")
    return javascript_violations(path)


def test_rejects_eval(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "value = eval(user_input)\n")
    assert any("eval() is forbidden" in finding for finding in findings)


def test_rejects_exec(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "exec(user_input)\n")
    assert any("exec() is forbidden" in finding for finding in findings)


def test_rejects_tempfile_mktemp(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import tempfile\npath = tempfile.mktemp()\n")
    assert any("mktemp() is race-prone" in finding for finding in findings)


def test_rejects_requests_verify_false(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import requests\nrequests.get(url, verify=False)\n")
    assert any("verify=False" in finding for finding in findings)


def test_rejects_constructed_requests_session_request_verify_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import requests\nrequests.Session().request('GET', url, verify=False)\n",
    )
    assert any("requests.Session.request" in finding and "verify=False" in finding for finding in findings)


def test_rejects_constructed_requests_session_method_verify_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import requests\nrequests.Session().get(url, verify=False)\n",
    )
    assert any("requests.Session.get" in finding and "verify=False" in finding for finding in findings)


def test_rejects_imported_requests_session_verify_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from requests import Session\nSession().post(url, verify=False)\n",
    )
    assert any("requests.Session.post" in finding and "verify=False" in finding for finding in findings)


def test_rejects_uniquely_bound_requests_session_verify_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import requests\nsession = requests.Session()\nsession.get(url, verify=False)\n",
    )
    assert any("requests.Session.get" in finding and "verify=False" in finding for finding in findings)


def test_rejects_aliased_constructor_bound_requests_session(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from requests import Session as SecureSession\n"
        "client = SecureSession()\n"
        "client.delete(url, verify=False)\n",
    )
    assert any("requests.Session.delete" in finding and "verify=False" in finding for finding in findings)


def test_allows_reassigned_session_name_to_avoid_unsafe_inference(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import requests\n"
        "session = requests.Session()\n"
        "session = custom_client\n"
        "session.get(url, verify=False)\n",
    )
    assert findings == []


def test_allows_parameter_shadowing_of_session_name(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import requests\n"
        "session = requests.Session()\n"
        "def fetch(session):\n"
        "    return session.get(url, verify=False)\n",
    )
    assert findings == []


def test_allows_bound_requests_session_with_verification(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import requests\nsession = requests.Session()\nsession.get(url, timeout=10)\n",
    )
    assert findings == []


def test_allows_constructed_requests_session_with_verification(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import requests\nrequests.Session().get(url, timeout=10)\n",
    )
    assert findings == []


def test_rejects_aliased_httpx_verify_false(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import httpx as hx\nhx.post(url, verify=False)\n")
    assert any("verify=False" in finding for finding in findings)


def test_rejects_httpx_client_with_disabled_verification(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import httpx\nclient = httpx.AsyncClient(verify=False)\n")
    assert any("verify=False" in finding for finding in findings)


def test_rejects_unverified_ssl_context(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import ssl\nctx = ssl._create_unverified_context()\n")
    assert any("disables certificate verification" in finding for finding in findings)


def test_rejects_jwt_signature_verification_disable(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'import jwt\npayload = jwt.decode(token, options={"verify_signature": False})\n',
    )
    assert any("must not disable signature verification" in finding for finding in findings)


def test_allows_verified_network_request(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import requests\nrequests.get(url, timeout=10)\n")
    assert findings == []


def test_js_rejects_eval(tmp_path: Path) -> None:
    findings = _scan_js(tmp_path, "const result = eval(userInput);\n")
    assert any("dynamic eval() is forbidden" in finding for finding in findings)


def test_js_rejects_function_constructor(tmp_path: Path) -> None:
    findings = _scan_js(tmp_path, "const fn = new Function('value', source);\n")
    assert any("Function constructor is forbidden" in finding for finding in findings)


def test_js_rejects_tls_reject_unauthorized_false(tmp_path: Path) -> None:
    findings = _scan_js(tmp_path, "const agent = new Agent({ rejectUnauthorized: false });\n")
    assert any("rejectUnauthorized:false" in finding for finding in findings)


def test_js_rejects_global_tls_verification_disable(tmp_path: Path) -> None:
    findings = _scan_js(tmp_path, "process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';\n")
    assert any("NODE_TLS_REJECT_UNAUTHORIZED=0" in finding for finding in findings)


def test_js_rejects_child_process_exec_method(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "import * as child_process from 'node:child_process';\nchild_process.exec(command);\n",
    )
    assert any("child_process.exec()/execSync()" in finding for finding in findings)


def test_js_rejects_required_child_process_exec(tmp_path: Path) -> None:
    findings = _scan_js(tmp_path, "require('child_process').exec(userInput);\n", suffix=".js")
    assert any("require('child_process').exec()" in finding for finding in findings)


def test_js_rejects_destructured_exec_alias(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "import { exec as runCommand } from 'node:child_process';\nrunCommand(input);\n",
    )
    assert any("imported child_process runCommand()" in finding for finding in findings)


def test_js_rejects_commonjs_destructured_exec_alias(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "const { execSync: run } = require('child_process');\nrun(input);\n",
        suffix=".js",
    )
    assert any("imported child_process run()" in finding for finding in findings)


def test_js_rejects_shell_enabled_child_process_spawn(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "import { spawn } from 'child_process';\nspawn(bin, args, { shell: true });\n",
    )
    assert any("shell:true is forbidden" in finding for finding in findings)


def test_js_allows_non_shell_spawn_and_normal_json_parse(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "import { spawn } from 'node:child_process';\n"
        "const child = spawn(bin, args, { shell: false });\n"
        "const value = JSON.parse(payload);\n",
    )
    assert findings == []


def test_js_ignores_eval_text_in_line_comment(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "// module-eval (which is documentation only)\nconst value = 1;\n",
    )
    assert findings == []


def test_js_ignores_security_patterns_in_block_comment(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "/* eval(userInput); child_process.exec(command); rejectUnauthorized: false */\n"
        "const value = 1;\n",
    )
    assert findings == []


def test_js_comment_mask_preserves_real_code_after_comment(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        "// harmless eval( text in docs\nconst result = eval(userInput);\n",
    )
    assert len([finding for finding in findings if "dynamic eval()" in finding]) == 1
    assert any(":2:" in finding for finding in findings)


def test_js_comment_markers_inside_strings_do_not_hide_following_code(tmp_path: Path) -> None:
    findings = _scan_js(
        tmp_path,
        'const url = "https://example.com/path";\nconst result = eval(userInput);\n',
    )
    assert any("dynamic eval() is forbidden" in finding for finding in findings)
