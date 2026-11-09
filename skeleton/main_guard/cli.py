"""Command-line entry points for main-guard.

``python -m skeleton.main_guard <command>`` dispatches to the component CLIs;
the thin wrappers in ``scripts/main_guard_*.py`` call the same functions.
Every command prints to stdout and uses exit codes suitable for CI:
``0`` clean, ``1`` findings (failure/drift/refusal), ``2`` usage or runtime error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Sequence

from .github import CommentPoster, GhCliTransport, GitHubClient, GitHubError, GitHubTransport
from .gitops import Git, GitError, parse_github_slug

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

TransportFactory = Callable[[], GitHubTransport]


def _default_transport() -> GitHubTransport:
    return GhCliTransport()


def resolve_repo_slug(git: Git, explicit: str | None) -> str:
    if explicit:
        return explicit
    slug = parse_github_slug(git.remote_url("origin"))
    if not slug:
        raise GitHubError("cannot infer owner/repo from origin; pass --repo owner/name")
    return slug


def _emit(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


# ------------------------------------------------------------------- watch
def build_watch_parser() -> argparse.ArgumentParser:
    from .watcher import DEFAULT_WATCHED_WORKFLOWS

    p = argparse.ArgumentParser(
        prog="main_guard_watch",
        description="Post-push watcher: attribute CI failures on main to commits/authors and render "
        "fix-forward notices. Dry-run by default; --post is required to comment on GitHub.",
    )
    p.add_argument("--repo", help="owner/name (default: parsed from the origin remote)")
    p.add_argument("--repo-dir", default=".", help="local clone used for history (default: .)")
    p.add_argument("--branch", default="main")
    p.add_argument("--ref", default=None, help="tip to inspect (default: origin/<branch>)")
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--since", help="inspect commits after this SHA (exclusive)")
    sel.add_argument("--last", type=int, help="inspect the last N first-parent commits")
    sel.add_argument("--sha", action="append", help="inspect exactly these commits (repeatable)")
    p.add_argument("--workflow", action="append", dest="workflows",
                   help=f"watched workflow name (repeatable; default: {', '.join(DEFAULT_WATCHED_WORKFLOWS)})")
    p.add_argument("--baseline-depth", type=int, default=25)
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("--output", help="also write the rendered report to this file")
    p.add_argument("--fetch", action="store_true", help="git fetch origin <branch> before selecting commits")
    p.add_argument("--update-state", action="store_true",
                   help="remember the newest settled commit so the next run only sees new pushes")
    p.add_argument("--fail-on-new", action="store_true", help="exit 1 when a newly introduced failure exists")
    p.add_argument("--post", action="store_true",
                   help="POST a commit comment for each commit with new failures (default: print only)")
    p.add_argument("--post-inherited", action="store_true",
                   help="with --post, also comment on commits whose failures are only inherited")
    return p


def watch_main(argv: Sequence[str] | None = None, *, transport_factory: TransportFactory | None = None) -> int:
    from .notice import render_commit_notice, render_watch_report
    from .watcher import DEFAULT_WATCHED_WORKFLOWS, PostPushWatcher, WatchState, post_notices, select_commits, settled_prefix

    args = build_watch_parser().parse_args(argv)
    factory = transport_factory or _default_transport
    try:
        git = Git(args.repo_dir)
        slug = resolve_repo_slug(git, args.repo)
        if args.fetch:
            git.run("fetch", "--quiet", "origin", args.branch)
        tip = args.ref or f"origin/{args.branch}"
        if git.try_rev_parse(tip) is None:
            tip = args.branch
        state = WatchState.for_repo(git, args.branch)
        if args.sha:
            shas = [git.try_rev_parse(s) or s for s in args.sha]
        elif args.since or args.last:
            shas = select_commits(git, until=tip, since=args.since, last=args.last)
        else:
            remembered = state.load()
            if remembered and git.try_rev_parse(remembered) and git.is_ancestor(remembered, tip):
                shas = select_commits(git, until=tip, since=remembered)
            else:
                shas = select_commits(git, until=tip, last=5)
        transport = factory()
        client = GitHubClient(slug, transport)
        watcher = PostPushWatcher(client, git=git, branch=args.branch,
                                  workflows=args.workflows or DEFAULT_WATCHED_WORKFLOWS,
                                  baseline_depth=args.baseline_depth)
        report = watcher.watch(shas)
    except (GitError, GitHubError, ValueError) as exc:
        print(f"main-guard watch: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.format == "json":
        payload: dict[str, object] = report.to_dict()
    else:
        payload = {}
    receipts: list[dict[str, object]] = []
    if args.post:
        try:
            poster = CommentPoster(slug, transport)
            receipts = post_notices(report, poster, render_commit_notice, include_inherited=args.post_inherited)
        except GitHubError as exc:
            print(f"main-guard watch: posting failed: {exc}", file=sys.stderr)
            return EXIT_ERROR
    if args.format == "json":
        payload["posted"] = receipts
        payload["dry_run"] = not args.post
        _emit(json.dumps(payload, indent=2, sort_keys=True), args.output)
    else:
        text = render_watch_report(report)
        if args.post:
            text += f"\nPosted {sum(1 for r in receipts if r.get('posted'))} notice(s).\n"
        else:
            text += "\n_Dry run: nothing was posted. Re-run with `--post` to comment on the commits._\n"
        _emit(text, args.output)
    if args.update_state:
        settled = settled_prefix(report)
        if settled:
            state.save(settled)
    if args.fail_on_new and report.has_new_failures:
        return EXIT_FINDINGS
    return EXIT_OK


COMMANDS: dict[str, Callable[..., int]] = {
    "watch": watch_main,
}


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print("usage: python -m skeleton.main_guard {" + ",".join(sorted(COMMANDS)) + "} [options]")
        return EXIT_OK if argv else EXIT_ERROR
    command = COMMANDS.get(argv[0])
    if command is None:
        print(f"unknown command {argv[0]!r}; expected one of {', '.join(sorted(COMMANDS))}", file=sys.stderr)
        return EXIT_ERROR
    return command(argv[1:])
