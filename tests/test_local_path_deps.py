"""Verify module pyproject.toml files use local path deps.

Both modules (tools-env-all and hooks-env-all) should depend on amplifier-env-common
via the local lib/ copy (not the git+https URL).

Directory layout (consolidated repo):
    modules/tools-env-all/pyproject.toml
    modules/hooks-env-all/pyproject.toml
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TOOLS_PYPROJECT = REPO_ROOT / "modules" / "tools-env-all" / "pyproject.toml"
HOOKS_PYPROJECT = REPO_ROOT / "modules" / "hooks-env-all" / "pyproject.toml"


class TestModulePyprojectLocalDeps:
    """Module pyproject.toml files must reference env-common via local path, not git URL."""

    def test_tools_no_git_url(self):
        content = TOOLS_PYPROJECT.read_text()
        assert "git+https://" not in content, (
            "tools-env-all/pyproject.toml still references git+https URL for env-common"
        )

    def test_hooks_no_git_url(self):
        content = HOOKS_PYPROJECT.read_text()
        assert "git+https://" not in content, (
            "hooks-env-all/pyproject.toml still references git+https URL for env-common"
        )

    def test_tools_depends_on_env_common(self):
        """tools-env-all must still declare amplifier-env-common as a dependency."""
        content = TOOLS_PYPROJECT.read_text()
        assert "amplifier-env-common" in content, (
            "tools-env-all/pyproject.toml lost its amplifier-env-common dependency"
        )

    def test_hooks_depends_on_env_common(self):
        """hooks-env-all must still declare amplifier-env-common as a dependency."""
        content = HOOKS_PYPROJECT.read_text()
        assert "amplifier-env-common" in content, (
            "hooks-env-all/pyproject.toml lost its amplifier-env-common dependency"
        )
