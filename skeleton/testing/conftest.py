"""Shared fixtures for composed offline-game delivery acceptance tests."""

pytest_plugins = (
    "skeleton.testing.test_app_offline_archive_signature",
    "skeleton.testing.test_app_offline_signed_progress_migration",
    "skeleton.testing.test_app_offline_policy_signed_progress_migration",
    "skeleton.testing.test_app_offline_policy_signed_delivery",
    "skeleton.testing.test_app_offline_policy_chain_delivery",
)
