"""Generated standard workspace protection rule factories."""

from __future__ import annotations

from skeleton.shells.workspace_txn.pathing import PathMatcher
from skeleton.shells.workspace_txn.rules import PathDenyRule

def protect_git_metadata() -> PathDenyRule:
    """Protect .git/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=(".git/**",)),
        code="protect_git_metadata",
        severity="critical",
    )


def protect_workflow_definitions() -> PathDenyRule:
    """Protect .github/workflows/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=(".github/workflows/**",)),
        code="protect_workflow_definitions",
        severity="critical",
    )


def protect_custom_actions() -> PathDenyRule:
    """Protect .github/actions/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=(".github/actions/**",)),
        code="protect_custom_actions",
        severity="critical",
    )


def protect_root_env() -> PathDenyRule:
    """Protect .env from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=(".env",)),
        code="protect_root_env",
        severity="critical",
    )


def protect_dotenv_variants() -> PathDenyRule:
    """Protect **/.env.* from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.env.*",)),
        code="protect_dotenv_variants",
        severity="critical",
    )


def protect_ssh_private_rsa() -> PathDenyRule:
    """Protect **/id_rsa from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/id_rsa",)),
        code="protect_ssh_private_rsa",
        severity="critical",
    )


def protect_ssh_private_ed25519() -> PathDenyRule:
    """Protect **/id_ed25519 from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/id_ed25519",)),
        code="protect_ssh_private_ed25519",
        severity="critical",
    )


def protect_netrc() -> PathDenyRule:
    """Protect **/.netrc from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.netrc",)),
        code="protect_netrc",
        severity="critical",
    )


def protect_npm_credentials() -> PathDenyRule:
    """Protect **/.npmrc from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.npmrc",)),
        code="protect_npm_credentials",
        severity="critical",
    )


def protect_pypi_credentials() -> PathDenyRule:
    """Protect **/.pypirc from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.pypirc",)),
        code="protect_pypi_credentials",
        severity="critical",
    )


def protect_cloud_credentials() -> PathDenyRule:
    """Protect **/credentials from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/credentials",)),
        code="protect_cloud_credentials",
        severity="critical",
    )


def protect_cloud_credentials_json() -> PathDenyRule:
    """Protect **/credentials.json from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/credentials.json",)),
        code="protect_cloud_credentials_json",
        severity="critical",
    )


def protect_secret_files() -> PathDenyRule:
    """Protect **/*secret* from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*secret*",)),
        code="protect_secret_files",
        severity="critical",
    )


def protect_token_files() -> PathDenyRule:
    """Protect **/*token* from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*token*",)),
        code="protect_token_files",
        severity="critical",
    )


def protect_credential_files() -> PathDenyRule:
    """Protect **/*credential* from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*credential*",)),
        code="protect_credential_files",
        severity="critical",
    )


def protect_pem_files() -> PathDenyRule:
    """Protect **/*.pem from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.pem",)),
        code="protect_pem_files",
        severity="critical",
    )


def protect_private_key_files() -> PathDenyRule:
    """Protect **/*.key from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.key",)),
        code="protect_private_key_files",
        severity="critical",
    )


def protect_pkcs12_files() -> PathDenyRule:
    """Protect **/*.p12 from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.p12",)),
        code="protect_pkcs12_files",
        severity="critical",
    )


def protect_pfx_files() -> PathDenyRule:
    """Protect **/*.pfx from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.pfx",)),
        code="protect_pfx_files",
        severity="critical",
    )


def protect_keystore_files() -> PathDenyRule:
    """Protect **/*.jks from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.jks",)),
        code="protect_keystore_files",
        severity="critical",
    )


def protect_terraform_state() -> PathDenyRule:
    """Protect **/*.tfstate from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.tfstate",)),
        code="protect_terraform_state",
        severity="critical",
    )


def protect_terraform_state_backup() -> PathDenyRule:
    """Protect **/*.tfstate.backup from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.tfstate.backup",)),
        code="protect_terraform_state_backup",
        severity="critical",
    )


def protect_kubeconfig() -> PathDenyRule:
    """Protect **/kubeconfig from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/kubeconfig",)),
        code="protect_kubeconfig",
        severity="critical",
    )


def protect_docker_auth() -> PathDenyRule:
    """Protect **/.docker/config.json from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.docker/config.json",)),
        code="protect_docker_auth",
        severity="critical",
    )


def protect_gnupg() -> PathDenyRule:
    """Protect **/.gnupg/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.gnupg/**",)),
        code="protect_gnupg",
        severity="critical",
    )


def protect_aws() -> PathDenyRule:
    """Protect **/.aws/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.aws/**",)),
        code="protect_aws",
        severity="critical",
    )


def protect_azure() -> PathDenyRule:
    """Protect **/.azure/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.azure/**",)),
        code="protect_azure",
        severity="critical",
    )


def protect_gcloud() -> PathDenyRule:
    """Protect **/.config/gcloud/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.config/gcloud/**",)),
        code="protect_gcloud",
        severity="critical",
    )


def protect_github_cli() -> PathDenyRule:
    """Protect **/.config/gh/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.config/gh/**",)),
        code="protect_github_cli",
        severity="critical",
    )


def protect_bash_history() -> PathDenyRule:
    """Protect **/.bash_history from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.bash_history",)),
        code="protect_bash_history",
        severity="error",
    )


def protect_zsh_history() -> PathDenyRule:
    """Protect **/.zsh_history from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.zsh_history",)),
        code="protect_zsh_history",
        severity="error",
    )


def protect_node_modules() -> PathDenyRule:
    """Protect **/node_modules/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/node_modules/**",)),
        code="protect_node_modules",
        severity="error",
    )


def protect_python_cache() -> PathDenyRule:
    """Protect **/__pycache__/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/__pycache__/**",)),
        code="protect_python_cache",
        severity="error",
    )


def protect_virtualenv() -> PathDenyRule:
    """Protect **/.venv/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.venv/**",)),
        code="protect_virtualenv",
        severity="error",
    )


def protect_venv() -> PathDenyRule:
    """Protect **/venv/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/venv/**",)),
        code="protect_venv",
        severity="error",
    )


def protect_pytest_cache() -> PathDenyRule:
    """Protect **/.pytest_cache/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.pytest_cache/**",)),
        code="protect_pytest_cache",
        severity="error",
    )


def protect_mypy_cache() -> PathDenyRule:
    """Protect **/.mypy_cache/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.mypy_cache/**",)),
        code="protect_mypy_cache",
        severity="error",
    )


def protect_ruff_cache() -> PathDenyRule:
    """Protect **/.ruff_cache/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.ruff_cache/**",)),
        code="protect_ruff_cache",
        severity="error",
    )


def protect_coverage_data() -> PathDenyRule:
    """Protect **/.coverage from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.coverage",)),
        code="protect_coverage_data",
        severity="warning",
    )


def protect_dist_artifacts() -> PathDenyRule:
    """Protect **/dist/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/dist/**",)),
        code="protect_dist_artifacts",
        severity="warning",
    )


def protect_build_artifacts() -> PathDenyRule:
    """Protect **/build/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/build/**",)),
        code="protect_build_artifacts",
        severity="warning",
    )


def protect_target_artifacts() -> PathDenyRule:
    """Protect **/target/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/target/**",)),
        code="protect_target_artifacts",
        severity="warning",
    )


def protect_idea_metadata() -> PathDenyRule:
    """Protect **/.idea/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.idea/**",)),
        code="protect_idea_metadata",
        severity="warning",
    )


def protect_vscode_metadata() -> PathDenyRule:
    """Protect **/.vscode/** from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.vscode/**",)),
        code="protect_vscode_metadata",
        severity="warning",
    )


def protect_ds_store() -> PathDenyRule:
    """Protect **/.DS_Store from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/.DS_Store",)),
        code="protect_ds_store",
        severity="warning",
    )


def protect_coverage_xml() -> PathDenyRule:
    """Protect **/coverage.xml from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/coverage.xml",)),
        code="protect_coverage_xml",
        severity="warning",
    )


def protect_pytest_junit() -> PathDenyRule:
    """Protect **/junit.xml from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/junit.xml",)),
        code="protect_pytest_junit",
        severity="warning",
    )


def protect_temp_files() -> PathDenyRule:
    """Protect **/*.tmp from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.tmp",)),
        code="protect_temp_files",
        severity="warning",
    )


def protect_swap_files() -> PathDenyRule:
    """Protect **/*.swp from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.swp",)),
        code="protect_swap_files",
        severity="warning",
    )


def protect_backup_files() -> PathDenyRule:
    """Protect **/*~ from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*~",)),
        code="protect_backup_files",
        severity="warning",
    )


def protect_compiled_python() -> PathDenyRule:
    """Protect **/*.pyc from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.pyc",)),
        code="protect_compiled_python",
        severity="error",
    )


def protect_compiled_python_opt() -> PathDenyRule:
    """Protect **/*.pyo from transactional mutation."""
    return PathDenyRule(
        PathMatcher(include=("**/*.pyo",)),
        code="protect_compiled_python_opt",
        severity="error",
    )


STANDARD_RULE_FACTORIES = (
    protect_git_metadata,
    protect_workflow_definitions,
    protect_custom_actions,
    protect_root_env,
    protect_dotenv_variants,
    protect_ssh_private_rsa,
    protect_ssh_private_ed25519,
    protect_netrc,
    protect_npm_credentials,
    protect_pypi_credentials,
    protect_cloud_credentials,
    protect_cloud_credentials_json,
    protect_secret_files,
    protect_token_files,
    protect_credential_files,
    protect_pem_files,
    protect_private_key_files,
    protect_pkcs12_files,
    protect_pfx_files,
    protect_keystore_files,
    protect_terraform_state,
    protect_terraform_state_backup,
    protect_kubeconfig,
    protect_docker_auth,
    protect_gnupg,
    protect_aws,
    protect_azure,
    protect_gcloud,
    protect_github_cli,
    protect_bash_history,
    protect_zsh_history,
    protect_node_modules,
    protect_python_cache,
    protect_virtualenv,
    protect_venv,
    protect_pytest_cache,
    protect_mypy_cache,
    protect_ruff_cache,
    protect_coverage_data,
    protect_dist_artifacts,
    protect_build_artifacts,
    protect_target_artifacts,
    protect_idea_metadata,
    protect_vscode_metadata,
    protect_ds_store,
    protect_coverage_xml,
    protect_pytest_junit,
    protect_temp_files,
    protect_swap_files,
    protect_backup_files,
    protect_compiled_python,
    protect_compiled_python_opt,
)


def standard_rules():
    """Instantiate the complete built-in repository protection family."""
    return tuple(factory() for factory in STANDARD_RULE_FACTORIES)
