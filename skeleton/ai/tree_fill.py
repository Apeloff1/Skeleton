"""Governed facade. Bodies stay in contrib until cutover. This path is the native owner."""

from importlib import import_module


def load():
    return import_module("ai_tree_fill")
