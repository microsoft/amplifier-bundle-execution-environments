"""Verify that env-common library was correctly copied into env-all/lib/.

This test ensures the consolidated structure has all expected modules,
backends, wrappers, tests, and pyproject.toml from the original env-common package.
"""

import os
from pathlib import Path

import pytest

# Root of the repo
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LIB_DIR = REPO_ROOT / "env-all" / "lib"
ORIGINAL_DIR = REPO_ROOT / "env-common"


class TestLibDirectoryExists:
    def test_lib_directory_exists(self):
        assert LIB_DIR.is_dir(), f"env-all/lib/ directory does not exist at {LIB_DIR}"

    def test_amplifier_env_common_package_exists(self):
        pkg = LIB_DIR / "amplifier_env_common"
        assert pkg.is_dir(), "amplifier_env_common/ package missing from lib/"


class TestCoreModulesPresent:
    """All core modules from env-common must be present in lib/."""

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
    """All test files from env-common must be copied."""

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


class TestContentMatchesOriginal:
    """Copied files must have identical content to originals."""

    def _source_py_files(self):
        """Yield (relative_path, original_path) for all .py files in env-common package."""
        pkg_dir = ORIGINAL_DIR / "amplifier_env_common"
        for root, _, files in os.walk(pkg_dir):
            for f in files:
                if f.endswith(".py"):
                    full = Path(root) / f
                    rel = full.relative_to(ORIGINAL_DIR)
                    yield str(rel), full

    def test_all_package_files_have_identical_content(self):
        """Every .py in env-common/amplifier_env_common/ must match its lib/ copy."""
        mismatches = []
        for rel, orig_path in self._source_py_files():
            copy_path = LIB_DIR / rel
            if not copy_path.exists():
                mismatches.append(f"MISSING: {rel}")
                continue
            if orig_path.read_text() != copy_path.read_text():
                mismatches.append(f"DIFFERS: {rel}")
        assert not mismatches, "Content mismatches:\n" + "\n".join(mismatches)

    def test_all_test_files_have_identical_content(self):
        """Every test file in env-common/tests/ must match its lib/tests/ copy."""
        mismatches = []
        tests_dir = ORIGINAL_DIR / "tests"
        for f in tests_dir.glob("*.py"):
            copy_path = LIB_DIR / "tests" / f.name
            if not copy_path.exists():
                mismatches.append(f"MISSING: tests/{f.name}")
                continue
            if f.read_text() != copy_path.read_text():
                mismatches.append(f"DIFFERS: tests/{f.name}")
        assert not mismatches, "Content mismatches:\n" + "\n".join(mismatches)

    def test_pyproject_toml_has_identical_content(self):
        orig = ORIGINAL_DIR / "pyproject.toml"
        copy = LIB_DIR / "pyproject.toml"
        assert copy.exists(), "lib/pyproject.toml missing"
        assert orig.read_text() == copy.read_text(), "pyproject.toml content differs"


class TestOriginalUntouched:
    """Original env-common/ must still be intact."""

    def test_original_package_still_exists(self):
        assert (ORIGINAL_DIR / "amplifier_env_common" / "__init__.py").is_file()

    def test_original_tests_still_exist(self):
        assert (ORIGINAL_DIR / "tests" / "test_models.py").is_file()

    def test_original_pyproject_still_exists(self):
        assert (ORIGINAL_DIR / "pyproject.toml").is_file()
