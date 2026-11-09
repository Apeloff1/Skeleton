"""Named policy profiles for common shell-plane execution classes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from skeleton.shells.runner import ShellPolicy


@dataclass(frozen=True)
class PolicyProfile:
    name: str
    description: str
    policy: ShellPolicy


class PolicyProfileCatalog:
    def __init__(self) -> None:
        self._profiles: dict[str, PolicyProfile] = {}

    def register(self, profile: PolicyProfile, *, replace: bool = False) -> None:
        if profile.name in self._profiles and not replace:
            raise ValueError(f"policy profile already registered: {profile.name}")
        self._profiles[profile.name] = profile

    def get(self, name: str) -> PolicyProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise KeyError(f"unknown shell policy profile: {name!r}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def snapshot(self) -> Mapping[str, PolicyProfile]:
        return dict(self._profiles)


def build_default_profiles(
    executables: Mapping[str, str],
    workspace: Path | str,
) -> PolicyProfileCatalog:
    """Build conservative baseline profiles without guessing tool-specific flags."""
    root = Path(workspace).expanduser().resolve(strict=True)
    catalog = PolicyProfileCatalog()
    catalog.register(
        PolicyProfile(
            "inspection",
            "Short read-oriented commands with no inherited environment or stdin.",
            ShellPolicy(
                executables=executables,
                cwd_roots=(root,),
                default_timeout=5.0,
                max_timeout=15.0,
                max_output_bytes=512 * 1024,
                max_input_bytes=0,
                max_env_bytes=4096,
                max_args=64,
                max_arg_bytes=16 * 1024,
            ),
        )
    )
    catalog.register(
        PolicyProfile(
            "build",
            "Bounded local build/test execution with explicit locale inheritance.",
            ShellPolicy(
                executables=executables,
                cwd_roots=(root,),
                allowed_env=frozenset({"LANG", "LC_ALL"}),
                inherited_env=frozenset({"LANG", "LC_ALL"}),
                default_timeout=30.0,
                max_timeout=300.0,
                max_output_bytes=8 * 1024 * 1024,
                max_input_bytes=512 * 1024,
                max_env_bytes=8192,
                max_args=256,
                max_arg_bytes=128 * 1024,
            ),
        )
    )
    catalog.register(
        PolicyProfile(
            "agent-tool",
            "Tight host-tool profile intended for model/tool adapters.",
            ShellPolicy(
                executables=executables,
                cwd_roots=(root,),
                default_timeout=10.0,
                max_timeout=60.0,
                max_output_bytes=1024 * 1024,
                max_input_bytes=64 * 1024,
                max_env_bytes=4096,
                max_args=96,
                max_arg_bytes=32 * 1024,
            ),
        )
    )
    return catalog
