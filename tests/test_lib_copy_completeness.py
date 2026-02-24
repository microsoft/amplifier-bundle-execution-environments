"""Verify that the shared library under lib/ is structurally complete.

This test ensures lib/ contains all expected modules, backends, wrappers,
tests, and pyproject.toml for the amplifier_env_common package.
"""

from pathlib import Path

import pytest

# Root of the repo (tests/ is directly under repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = REPO_ROOT / "lib"


class TestLibDirectoryExists:
    def test_lib_directory_exists(self):
        assert LIB_DIR.is_dir(), f"lib/ directory does not exist at {LIB_DIR}"

    def test_amplifier_env_common_package_exists(self):
        pkg = LIB_DIR / "amplifier_env_common"
        assert pkg.is_dir(), "amplifier_env_common/ package missing from lib/"


class TestCoreModulesPresent:
    """All core modules must be present in lib/."""

    EXPECTED_MODULES = [
        "__init__.py",
        "models.py",
        "schemas.py",
        "protocol.py",
        "registry.py",
        "env_filter.py",
    ]

    @pytest.mark.parametrize("module", EXPECTED_MODULES)
    def test_core_module_exists(self, module):
        path = LIB_DIR / "amplifier_env_common" / module
        assert path.is_file(), (
            f"Core module {module} missing from lib/amplifier_env_common/"
        )


class TestBackendsPresent:
    """All backend modules must be present."""

    EXPECTED_BACKENDS = [
        "__init__.py",
        "local.py",
        "docker.py",
        "ssh.py",
    ]

    @pytest.mark.parametrize("backend", EXPECTED_BACKENDS)
    def test_backend_exists(self, backend):
        path = LIB_DIR / "amplifier_env_common" / "backends" / backend
        assert path.is_file(), (
            f"Backend {backend} missing from lib/amplifier_env_common/backends/"
        )


class TestWrappersPresent:
    """All wrapper modules must be present."""

    EXPECTED_WRAPPERS = [
        "__init__.py",
        "logging_wrapper.py",
        "readonly_wrapper.py",
    ]

    @pytest.mark.parametrize("wrapper", EXPECTED_WRAPPERS)
    def test_wrapper_exists(self, wrapper):
        path = LIB_DIR / "amplifier_env_common" / "wrappers" / wrapper
        assert path.is_file(), (
            f"Wrapper {wrapper} missing from lib/amplifier_env_common/wrappers/"
        )


class TestPyprojectPresent:
    def test_pyproject_toml_exists(self):
        path = LIB_DIR / "pyproject.toml"
        assert path.is_file(), "pyproject.toml missing from lib/"


class TestTestsPresent:
    """All test files must be present in lib/tests/."""

    EXPECTED_TESTS = [
        "test_docker_backend.py",
        "test_env_filter.py",
        "test_local_backend.py",
        "test_logging_wrapper.py",
        "test_models.py",
        "test_protocol.py",
        "test_readonly_wrapper.py",
        "test_registry.py",
        "test_scaffold.py",
        "test_schemas.py",
        "test_ssh_backend.py",
    ]

    @pytest.mark.parametrize("test_file", EXPECTED_TESTS)
    def test_test_file_exists(self, test_file):
        path = LIB_DIR / "tests" / test_file
        assert path.is_file(), f"Test file {test_file} missing from lib/tests/"
