"""Reusable strict argument constraints for toolchain contracts."""

from __future__ import annotations

from skeleton.shells.arguments import ArgumentPolicy, OptionRule, ValueConstraint


SAFE_TOKEN = ValueConstraint(
    pattern=r"[^\x00\r\n]{1,4096}",
    min_length=1,
    max_length=4096,
)

SHORT_TOKEN = ValueConstraint(
    pattern=r"[^\x00\r\n]{1,512}",
    min_length=1,
    max_length=512,
)

IDENTIFIER = ValueConstraint(
    pattern=r"[A-Za-z0-9][A-Za-z0-9_.:/+@-]{0,255}",
    min_length=1,
    max_length=256,
)

RELATIVE_PATH = ValueConstraint(
    pattern=r"(?!/)(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))[^\x00\r\n]{1,4096}",
    min_length=1,
    max_length=4096,
)

PYTHON_MODULE = ValueConstraint(
    pattern=r"[A-Za-z_][A-Za-z0-9_.]*",
    min_length=1,
    max_length=512,
)

PACKAGE_SPEC = ValueConstraint(
    pattern=r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?(?:==|!=|~=|>=|<=|>|<)?[A-Za-z0-9_.+!-]*",
    min_length=1,
    max_length=512,
)

TEST_SELECTOR = ValueConstraint(
    pattern=r"(?!/)(?!.*(?:^|/)\.\.(?:/|$))[^\x00\r\n]{1,2048}",
    min_length=1,
    max_length=2048,
)

GIT_REF = ValueConstraint(
    pattern=r"(?!-)(?!.*\.\.)(?!.*@\{)(?!.*[~^:?*\[\\])[^\x00\x20\x7f]{1,255}",
    min_length=1,
    max_length=255,
)

HEX_SHA = ValueConstraint(
    pattern=r"[0-9a-fA-F]{7,64}",
    min_length=7,
    max_length=64,
)

INTEGER = ValueConstraint(
    pattern=r"[0-9]{1,12}",
    min_length=1,
    max_length=12,
)

URL_HTTPS = ValueConstraint(
    pattern=r"https://[^\x00\r\n ]{1,2040}",
    min_length=8,
    max_length=2048,
)


def option(name: str, *, value: ValueConstraint | None = None, repeatable: bool = False) -> OptionRule:
    return OptionRule(
        name=name,
        takes_value=value is not None,
        repeatable=repeatable,
        value=value or ValueConstraint(),
    )


def subcommand_policy(
    subcommand: str,
    *,
    options: tuple[OptionRule, ...] = (),
    positional: tuple[ValueConstraint, ...] = (),
    variadic: ValueConstraint | None = None,
    min_positionals: int | None = None,
    max_positionals: int | None = None,
    allow_double_dash: bool = True,
    max_total_args: int = 128,
    max_total_bytes: int = 65_536,
) -> ArgumentPolicy:
    first = ValueConstraint(choices=frozenset({subcommand}), min_length=1, max_length=len(subcommand))
    explicit = (first, *positional)
    minimum = len(explicit) if min_positionals is None else min_positionals
    maximum = max_positionals
    if maximum is None and variadic is None:
        maximum = len(explicit)
    return ArgumentPolicy(
        options={rule.name: rule for rule in options},
        positional=explicit,
        variadic=variadic,
        min_positionals=minimum,
        max_positionals=maximum,
        allow_double_dash=allow_double_dash,
        allow_option_equals=True,
        max_total_args=max_total_args,
        max_total_bytes=max_total_bytes,
    )
