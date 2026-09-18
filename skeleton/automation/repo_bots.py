"""Bounded repository bots powered by a configurable model API.

Model output is untrusted. Proposals are path-bounded, validated in a
credential-free Git-less workspace, and published from a separate clean clone.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import PurePosixPath

from .bot_manager import load_state, record_result, save_state, select_base_due
from .bot_safety import publish_pull_request, run_safe_tests, validation_workspace
from .free_model import FreeModelClient, ModelError

API = "https://api.github.com"
SAFE_PREFIXES = ("skeleton/", "tests/", "docs/")
BLOCKED_PREFIXES = (".github/", ".git/", ".env", "secrets/", "deploy/")
MAX_FILE = 80_000
MAX_FILES = 6
MAX_SUMMARY = 4_000
MAX_TEST_COMMAND = 300


@dataclass(frozen=True)
class BotSpec:
    name: str
    purpose: str


BOTS = {
    "triage": BotSpec("triage", "triage open issues and propose small, testable repairs"),
    "ci": BotSpec("ci", "analyze recent failed CI and propose a focused repair"),
    "security": BotSpec("security", "find likely security regressions and propose tests or bounded fixes"),
    "cleanup": BotSpec("cleanup", "find safe repository cleanup opportunities in docs/tests/code"),
}


def gh(path: str, token: str) -> object:
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Skeleton-Repo-Bots/2.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read(5_000_000).decode("utf-8"))


def get_text(path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"HEAD:{path}"],
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=20,
    )[:MAX_FILE]


def repo_context() -> str:
    files: list[str] = []
    for root, _, names in os.walk("skeleton"):
        for name in names:
            if not name.endswith((".py", ".md", ".yaml", ".yml", ".json")):
                continue
            path = os.path.join(root, name).replace(os.sep, "/")
            if "/__pycache__/" not in path:
                files.append(path)
            if len(files) >= 60:
                break
        if len(files) >= 60:
            break
    excerpts = []
    for path in files:
        try:
            text = get_text(path)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        excerpts.append(f"\n--- {path} ---\n{text[:5000]}")
    return "".join(excerpts)


def safe_path(path: str) -> bool:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        return False
    p = PurePosixPath(path)
    if path.startswith("/") or ".." in p.parts or any(path.startswith(x) for x in BLOCKED_PREFIXES):
        return False
    return any(path.startswith(prefix) for prefix in SAFE_PREFIXES)


def extract_plan(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("model did not return JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model plan must be an object")

    summary = data.get("summary", "")
    if not isinstance(summary, str):
        raise ValueError("summary must be text")
    data["summary"] = summary[:MAX_SUMMARY]

    files = data.get("files", [])
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ValueError("invalid file count")
    clean = []
    seen: set[str] = set()
    for item in files:
        path = item.get("path") if isinstance(item, dict) else None
        content = item.get("content") if isinstance(item, dict) else None
        if (
            not safe_path(path)
            or not isinstance(content, str)
            or len(content.encode("utf-8")) > MAX_FILE
            or path in seen
        ):
            raise ValueError(f"unsafe proposed file: {path!r}")
        seen.add(path)
        clean.append({"path": path, "content": content})
    data["files"] = clean

    tests = data.get("tests", [])
    if not isinstance(tests, list) or len(tests) > 3:
        raise ValueError("invalid test command list")
    for command in tests:
        if not isinstance(command, str) or len(command) > MAX_TEST_COMMAND:
            raise ValueError("invalid test command")
    data["tests"] = tests
    return data


def model_prompt(spec: BotSpec, context: str, signal: str) -> str:
    return f"""You are the {spec.name} maintenance bot for Apeloff1/Skeleton.
Goal: {spec.purpose}.

Safety contract:
- Work only on the repository supplied below.
- Never weaken authentication, authorization, CORS, secret scanning, malware scanning, required checks, or branch protection.
- Never edit .github workflows, deployment files, secrets, or environment files.
- Do not invent APIs or dependencies.
- Prefer a small regression test plus the smallest implementation change.
- If evidence is insufficient, return an empty files list and explain why.
- Tests may only be: python tests/run_unit.py, python -m compileall -q skeleton,
  or python -m pytest -q followed only by tests/ or skeleton/testing/ paths.

Return ONLY JSON with this shape:
{{"summary":"...","files":[{{"path":"skeleton/...py","content":"complete file contents"}}],"tests":["python -m pytest -q tests/test_name.py"]}}

Current signal:
{signal[:12000]}

Repository context:
{context[:90000]}
"""


def signal_for(mode: str, token: str) -> str:
    if mode == "triage":
        issues = gh("/repos/Apeloff1/Skeleton/issues?state=open&per_page=20", token)
        return json.dumps([x for x in issues if "pull_request" not in x][:12], indent=2)  # type: ignore[union-attr]
    if mode == "ci":
        runs = gh("/repos/Apeloff1/Skeleton/actions/runs?per_page=20", token)
        return json.dumps(runs, indent=2)[:30000]
    if mode == "security":
        return "Review source for concrete security defects and add regression coverage. Do not claim scanner findings without evidence."
    return "Review tracked repository files for dead, duplicated, stale, or misleading code/docs that can be safely cleaned."


def _run_one(mode: str, token: str, base_sha: str) -> str:
    spec = BOTS[mode]
    client = FreeModelClient()
    signal = signal_for(mode, token)
    plan = extract_plan(
        client.chat(
            "You are a conservative software maintenance agent. Return machine-readable JSON only.",
            model_prompt(spec, repo_context(), signal),
        )
    )
    if not plan["files"]:
        print(json.dumps({"status": "no-change", "bot": mode, "summary": plan["summary"]}, indent=2))
        return "no-change"

    requires_tests = any(item["path"].endswith(".py") for item in plan["files"])
    with validation_workspace(plan["files"]) as work:
        run_safe_tests(plan["tests"], require=requires_tests, cwd=work)

    branch = f"bot/{mode}-{os.environ.get('GITHUB_RUN_ID', 'local')}"
    title = f"bot({mode}): bounded repository maintenance"
    publish_pull_request(
        files=plan["files"],
        token=token,
        base_sha=base_sha,
        branch=branch,
        title=title,
        body=(
            plan["summary"]
            + "\n\nGenerated by Skeleton Repo Bots; model output was validated without credentials "
              "and all normal repository checks remain authoritative."
        ),
        commit_message=title,
    )
    print(json.dumps({"status": "pull-request-created", "bot": mode, "branch": branch}, indent=2))
    return "pull-request-created"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all", *BOTS], default="all")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN is required")
        return 2

    try:
        base_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=15
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("unable to establish trusted base commit")
        return 2

    state = load_state()
    modes = select_base_due(state) if args.mode == "all" else [args.mode]
    if not modes:
        save_state(state)
        print(json.dumps({"status": "cooldown", "bots": []}, indent=2))
        return 0

    failed = False
    for mode in modes:
        try:
            _run_one(mode, token, base_sha)
            record_result(state, mode, success=True)
        except (
            ModelError,
            ValueError,
            RuntimeError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            record_result(state, mode, success=False)
            failed = True
            print(f"repo bot {mode} stopped safely: {exc}")
    save_state(state)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
