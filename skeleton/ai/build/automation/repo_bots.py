"""Bounded repository bots powered by a configurable free-tier model API.

The runner is deliberately fail-closed: it never writes to main, never edits
workflow files, never handles secrets, and only opens a PR after local checks.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .free_model import FreeModelClient, ModelError

API = "https://api.github.com"
SAFE_PREFIXES = ("skeleton/", "tests/", "docs/")
BLOCKED_PREFIXES = (".github/", ".git/", ".env", "secrets/", "deploy/")
MAX_FILE = 80_000
MAX_FILES = 6


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
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "Skeleton-Repo-Bots/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read(5_000_000).decode("utf-8"))


def get_text(path: str) -> str:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], text=True, stderr=subprocess.DEVNULL)[:MAX_FILE]


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
        except subprocess.CalledProcessError:
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
    files = data.get("files", [])
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ValueError("invalid file count")
    clean = []
    for item in files:
        path = item.get("path") if isinstance(item, dict) else None
        content = item.get("content") if isinstance(item, dict) else None
        if not safe_path(path) or not isinstance(content, str) or len(content.encode()) > MAX_FILE:
            raise ValueError(f"unsafe proposed file: {path!r}")
        clean.append({"path": path, "content": content})
    data["files"] = clean
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

Return ONLY JSON with this shape:
{{"summary":"...","files":[{{"path":"skeleton/...py","content":"complete file contents"}}],"tests":["command ..."]}}

Current signal:
{signal[:12000]}

Repository context:
{context[:90000]}
"""


def validate_generated_files(plan: dict) -> None:
    """Perform non-executing syntax validation on model-generated Python."""
    for item in plan["files"]:
        path = item["path"]
        if path.endswith(".py"):
            try:
                ast.parse(item["content"], filename=path)
            except SyntaxError as exc:
                raise RuntimeError(f"generated Python is invalid: {path}") from exc


def write_plan(plan: dict) -> None:
    for item in plan["files"]:
        os.makedirs(os.path.dirname(item["path"]), exist_ok=True)
        with open(item["path"], "w", encoding="utf-8", newline="") as handle:
            handle.write(item["content"])


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["triage", "ci", "security", "cleanup"], default="triage")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN is required")
        return 2
    try:
        client = FreeModelClient()
        signal = signal_for(args.mode, token)
        plan = extract_plan(client.chat(
            "You are a conservative software maintenance agent. Return machine-readable JSON only.",
            model_prompt(BOTS[args.mode], repo_context(), signal),
        ))
        if not plan["files"]:
            print(json.dumps({"status": "no-change", "summary": plan.get("summary", "")}, indent=2))
            return 0
        validate_generated_files(plan)
        write_plan(plan)
        branch = f"bot/{args.mode}-{os.environ.get('GITHUB_RUN_ID', 'local')}"
        hooks = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "skeleton-empty-hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "config", "core.hooksPath", str(hooks)], check=True)
        subprocess.run(["git", "checkout", "-b", branch], check=True)
        subprocess.run(["git", "config", "user.name", "skeleton-repo-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "skeleton-repo-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", "--", *[x["path"] for x in plan["files"]]], check=True)
        subprocess.run(["git", "commit", "--no-verify", "-m", f"bot({args.mode}): bounded repository maintenance"], check=True)
        repo = os.environ.get("GITHUB_REPOSITORY", "Apeloff1/Skeleton")
        subprocess.run(["git", "remote", "set-url", "--push", "origin", f"https://github.com/{repo}.git"], check=True)
        env = {**os.environ, "GH_TOKEN": token}
        subprocess.run(["gh", "auth", "setup-git"], check=True, env=env)
        subprocess.run(["git", "push", "--set-upstream", "origin", branch], check=True, env=env)
        subprocess.run([
            "gh", "pr", "create", "--repo", "Apeloff1/Skeleton", "--base", "main", "--head", branch,
            "--title", f"bot({args.mode}): bounded repository maintenance",
            "--body", plan.get("summary", "Automated bounded maintenance proposal.") + "\n\nGenerated by Skeleton Repo Bots; all normal repository checks remain authoritative.",
        ], check=True, env=env)
        print(json.dumps({"status": "pull-request-created", "branch": branch, "summary": plan.get("summary", "")}, indent=2))
    except (ModelError, ValueError, RuntimeError, subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
        print(f"repo bot stopped safely: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
