"""Exact original Emerald binary transport for five review-only GitHub drafts.

Use an existing authenticated checkout of Apeloff1/Skeleton. No credentials
are read by this program; Git uses its configured authentication. No force
push, release, merge, pin change, filters or substitute assets are permitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "assets/emerald/20261117-r1/"
MANIFEST = PREFIX + "publication-manifest.json"
PIN = "frontend/src/features/Jeeves/companion/emeraldAssetPin.json"
GROUPS = ("web", "source", "model-a", "model-b", "model-c")
MAX_CHUNK = 32 * 1024**2
ALLOWED_REMOTES = {
    "https://github.com/Apeloff1/Skeleton",
    "https://github.com/Apeloff1/Skeleton.git",
    "git@github.com:Apeloff1/Skeleton.git",
    "ssh://git@github.com/Apeloff1/Skeleton.git",
}
HEX = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest(raw, pin):
    require(len(raw) <= 65536, "manifest oversized")
    m = json.loads(raw)
    require(m["schema"] == "skeleton.emerald.git-publication.v1"
            and m["asset_set"] == pin["assetSet"] == "emerald-20261117-r1"
            and m["chunk_max_bytes"] == MAX_CHUNK, "manifest identity")
    expected = {
        "web": ("emerald-skeleton-web-assets.zip", pin["web"]["bytes"], pin["web"]["sha256"]),
        "source": ("emerald-atelier-fold-source.zip", pin["native"]["sourceBytes"], pin["native"]["sourceSha256"]),
        "model": ("emerald_continuum.glb", pin["native"]["modelBytes"], pin["native"]["modelSha256"]),
    }
    require([a["role"] for a in m["assets"]] == list(expected), "asset roles")
    groups = {g: [] for g in GROUPS}
    for asset in m["assets"]:
        role = asset["role"]
        name, size, sha = expected[role]
        require((asset["name"], asset["bytes"], asset["sha256"]) == (name, size, sha)
                and HEX.fullmatch(sha), "asset pin mismatch")
        remaining = size
        for i, row in enumerate(asset["chunks"]):
            group = role if role != "model" else GROUPS[2 + min(i // 5, 2)]
            part = min(MAX_CHUNK, remaining)
            require(part > 0 and row["bytes"] == part and row["offset"] == size - remaining
                    and row["group"] == group and HEX.fullmatch(row["sha256"])
                    and row["path"] == PREFIX + group + "/" + name + f".part{i+1:03d}",
                    "invalid chunk contract")
            remaining -= part
            groups[group].append(row)
        require(remaining == 0, "incomplete asset coverage")
    require([g["id"] for g in m["groups"]] == list(GROUPS), "invalid group ordering")
    for group in m["groups"]:
        key = group["id"]
        require(group == {"id": key, "branch": f"assets/emerald-original-{key}-20261117",
                          "bytes": sum(r["bytes"] for r in groups[key]), "chunks": len(groups[key])},
                "group contract mismatch")
        require(groups[key], "empty group")
    return m, groups


def verified(data, row):
    require(len(data) == row["bytes"] and digest(data) == row["sha256"],
            "chunk identity mismatch: " + row["path"])
    return data


def bundle_rows(bundle, rows, raw):
    """Read only exact named ZIP members; no archive extraction."""
    expected = {"publication-manifest.json", *(r["path"] for r in rows)}
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        require(len(infos) == len(expected) and {i.filename for i in infos} == expected,
                "unexpected bundle inventory")
        for info in infos:
            require(not info.is_dir() and not info.flag_bits & 1, "unsafe bundle member")
        info = archive.getinfo("publication-manifest.json")
        require(info.file_size == len(raw) and archive.read(info) == raw, "bundle manifest mismatch")
        for row in rows:
            info = archive.getinfo(row["path"])
            require(info.file_size == row["bytes"], "bundle member length")
            yield row, verified(archive.read(info), row)


def git(repo, *args, data=None, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=data, stdout=subprocess.PIPE,
        check=True, env=env,
    ).stdout


def git_id(data):
    value = data.decode("ascii").strip()
    require(SHA.fullmatch(value), "invalid Git object identity")
    return value


def check_remote(repo):
    # Validate both fetch AND push URL: a separate pushurl must not redirect bytes.
    for args in (("remote", "get-url", "origin"), ("remote", "get-url", "--push", "origin")):
        url = git(repo, *args).decode().strip()
        require(url in ALLOWED_REMOTES, "origin is not the authorized Skeleton repository")


def fetch_group(repo, group, raw):
    branch = f"assets/emerald-original-{group}-20261117"
    ref = "refs/heads/" + branch
    git(repo, "fetch", "--no-tags", "origin", ref)
    head = git_id(git(repo, "rev-parse", "FETCH_HEAD"))
    require(git(repo, "show", head + ":" + MANIFEST) == raw, "draft manifest differs")
    return ref, head


def publish_group(repo, group, bundle, rows, raw, *, sign=False):
    ref, head = fetch_group(repo, group, raw)
    with tempfile.TemporaryDirectory(prefix="emerald-git-index-") as scratch:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(scratch) / "index"))
        git(repo, "read-tree", head, env=env)
        for row, data in bundle_rows(bundle, rows, raw):
            path = row["path"]
            # Raw Git objects, not worktree conversions (e.g. CRLF or LFS).
            blob = git_id(git(repo, "hash-object", "-w", "--no-filters", "--stdin", data=data))
            old = git(repo, "ls-tree", head, "--", path).decode().strip()
            if old:
                require(old == f"100644 blob {blob}\t{path}", "refusing to replace existing chunk")
                continue
            git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
        tree = git_id(git(repo, "write-tree", env=env))
    base_tree = git_id(git(repo, "rev-parse", head + "^{tree}"))
    if tree == base_tree:
        actual = git(repo, "ls-remote", "--exit-code", "origin", ref).decode().split()
        require(actual == [head, ref], "remote changed during no-op; revalidate")
        return head
    args = ["commit-tree", tree, "-p", head, "-m", "assets(dragon): publish exact original " + group + " chunks"]
    if sign:
        args.append("-S")
    commit = git_id(git(repo, *args))
    # Ordinary fast-forward only. A concurrent branch update causes rejection.
    git(repo, "push", "origin", commit + ":" + ref)
    actual = git(repo, "ls-remote", "--exit-code", "origin", ref).decode().split()
    require(actual == [commit, ref], "remote changed after push; revalidate")
    return commit


def write_originals(m, target, read):
    """Restore all three files or no target directory; trusted parent required."""
    target = Path(target).absolute()
    require(target.parent.is_dir() and not target.parent.is_symlink(), "trusted existing output parent required")
    require(not os.path.lexists(target), "output already exists")
    required = sum(a["bytes"] for a in m["assets"])
    require(shutil.disk_usage(target.parent).free >= required + MAX_CHUNK, "insufficient disk space")
    work = Path(tempfile.mkdtemp(prefix=".emerald-publication-", dir=target.parent))
    try:
        for asset in m["assets"]:
            sha = hashlib.sha256()
            length = 0
            with (work / asset["name"]).open("xb") as output:
                for row in asset["chunks"]:
                    data = verified(read(row), row)
                    output.write(data)
                    sha.update(data)
                    length += len(data)
                output.flush()
                os.fsync(output.fileno())
            require(length == asset["bytes"] and sha.hexdigest() == asset["sha256"], "whole asset pin mismatch")
        require(not os.path.lexists(target), "concurrent output publication")
        os.rename(work, target)
    finally:
        if work.exists():
            shutil.rmtree(work)


def collect(repo, m, raw, target):
    heads = {group: fetch_group(repo, group, raw)[1] for group in GROUPS}
    def read(row):
        obj = heads[row["group"]] + ":" + row["path"]
        require(int(git(repo, "cat-file", "-s", obj)) == row["bytes"], "remote blob size mismatch")
        return git(repo, "cat-file", "blob", obj)
    write_originals(m, target, read)
    return heads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("publish", "collect", "verify-bundles", "verify-tree"))
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--bundles", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--group", choices=GROUPS, action="append")
    parser.add_argument("--sign", action="store_true")
    args = parser.parse_args()
    raw = (ROOT / MANIFEST).read_bytes()
    pin = json.loads((ROOT / PIN).read_text(encoding="utf-8"))
    m, groups = manifest(raw, pin)
    chosen = args.group or list(GROUPS)
    if args.mode == "verify-tree":
        if not args.group:
            parser.error("verify-tree requires explicit group(s)")
        for group in chosen:
            for row in groups[group]:
                path = args.repo / row["path"]
                require(path.is_file() and not path.is_symlink() and path.stat().st_size == row["bytes"], "missing or unsafe chunk: " + row["path"])
                verified(path.read_bytes(), row)
        print(json.dumps({"verified_checkout_groups": chosen, "release_qualified": False}, indent=2))
        return
    if args.mode == "collect":
        if args.output is None or args.group is not None:
            parser.error("collect requires --output and restores all groups")
        check_remote(args.repo)
        print(json.dumps({"verified_remote_heads": collect(args.repo, m, raw, args.output)}, indent=2))
        return
    if args.bundles is None:
        parser.error("--bundles directory required")
    # Verify every selected bundle before performing any external write.
    for group in chosen:
        for _ in bundle_rows(args.bundles / (group + "-publication.zip"), groups[group], raw):
            pass
    if args.mode == "verify-bundles":
        print(json.dumps({"verified_groups": chosen, "binary_publication": False}, indent=2))
        return
    check_remote(args.repo)
    for group in chosen:
        head = publish_group(args.repo, group, args.bundles / (group + "-publication.zip"),
                             groups[group], raw, sign=args.sign)
        print(json.dumps({"group": group, "published_head": head}), flush=True)


if __name__ == "__main__":
    main()
