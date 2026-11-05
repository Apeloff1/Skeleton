"""Content-addressed offline AI model installation.

Read the source-bound ecosystem archive in one pass and install only approved
model artifacts. Never run code from an archive or assume a hash is a signature.
"""
from .installer import InstallError, InstallReceipt, install_approved_model
from .doctor import InstalledModelReport, inspect_installed_model

__all__ = ["InstallError", "InstallReceipt", "install_approved_model",
           "InstalledModelReport", "inspect_installed_model"]
