"""Verify module pyproject.toml files use local path deps and Makefile installs from env-all/lib/.

After Phase 4.4 Task A.2+A.3, both modules should depend on amplifier-env-common
via the local lib/ copy (not the git+https URL), and the Makefile should install
from env-all/lib/ (not env-common/).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

TOOLS_PYPROJECT = REPO_ROOT / "env-all" / "modules" / "tools-env-all" / "pyproject.toml"
HOOKS_PYPROJECT = REPO_ROOT / "env-all" / "modules" / "hooks-env-all" / "pyproject.toml"
MAKEFILE = REPO_ROOT / "Makefile"


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


class TestMakefileUsesLocalLib:
    """Makefile must install from env-all/lib/, not env-common/."""

    def test_makefile_installs_env_all_lib(self):
        content = MAKEFILE.read_text()
        assert "env-all/lib" in content, "Makefile does not install from env-all/lib"

    def test_makefile_no_standalone_env_common_install(self):
        """Makefile should not install from the top-level env-common/ directory."""
        content = MAKEFILE.read_text()
        for line in content.splitlines():
            line = line.strip()
            # Skip comments
            if line.startswith("#"):
                continue
            # The old pattern: 'uv pip install -e env-common'
            # Must not appear as a standalone install target
            if "uv pip install" in line and "env-common" in line:
                # Allow 'env-all/lib' references (that's the new location)
                assert "env-all/lib" in line, (
                    f"Makefile still installs from standalone env-common/: {line!r}"
                )

    def test_makefile_test_target_includes_lib_tests(self):
        """Test target must run tests from env-all/lib/tests/."""
        content = MAKEFILE.read_text()
        assert "env-all/lib/tests/" in content, (
            "Makefile test target does not include env-all/lib/tests/"
        )

    def test_makefile_test_target_no_standalone_env_common_tests(self):
        """Test target must not run tests from top-level env-common/tests/."""
        content = MAKEFILE.read_text()
        # Find lines in the test target
        in_test_target = False
        for line in content.splitlines():
            if line.startswith("test:"):
                in_test_target = True
                continue
            if in_test_target:
                # End of target: non-tab line that's not empty
                if line and not line.startswith("\t") and not line.startswith(" "):
                    break
                if "env-common/tests/" in line:
                    raise AssertionError(
                        f"Makefile test target still references env-common/tests/: {line!r}"
                    )
