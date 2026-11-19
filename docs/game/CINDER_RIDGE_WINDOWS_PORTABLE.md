# Windows consumer entry point for the portable original game

The consumer bundle command now publishes two create-only files to the user's
local Cinder Ridge exports directory: a bounded original-game Python .pyz and
a same-directory .cmd launcher. Copy both to the Windows laptop and double
click the .cmd. It locates py -3 or python, launches the packaged game and
uses an ASCII terminal fallback for console compatibility.

The command has no dynamic shell arguments or untrusted executable path:
the .pyz name is a fixed prefix plus a SHA-256-derived hexadecimal suffix.
It never overwrites existing package files. If either publication fails,
it reports an error and leaves existing files untouched.

This is a runnable Python-source distribution requiring Python 3.11+, not a
native executable, a signed installer, or proof of Windows device readiness.
Validate with actual Windows consumer install, save/quit/restart, replay
export, security and exact-head CI before release.
