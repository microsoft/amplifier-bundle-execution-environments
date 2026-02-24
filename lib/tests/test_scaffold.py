"""Tests for env-common package scaffold structure."""

import pathlib

import tomllib


ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestDirectoryStructure:
    """Verify env-common has the expected files."""

    def test_pyproject_toml_exists(self):
        assert (ROOT / "pyproject.toml").is_file()

    def test_package_init_exists(self):
        assert (ROOT / "amplifier_env_common" / "__init__.py").is_file()

    def test_models_module_exists(self):
        assert (ROOT / "amplifier_env_common" / "models.py").is_file()

    def test_schemas_module_exists(self):
        assert (ROOT / "amplifier_env_common" / "schemas.py").is_file()


class TestPyprojectToml:
    """Verify pyproject.toml has correct metadata."""

    def _load(self) -> dict:
        return tomllib.loads((ROOT / "pyproject.toml").read_text())

    def test_package_name(self):
        data = self._load()
        assert data["project"]["name"] == "amplifier-env-common"

    def test_version(self):
        data = self._load()
        assert data["project"]["version"] == "0.1.0"

    def test_requires_python(self):
        data = self._load()
        assert data["project"]["requires-python"] == ">=3.11"

    def test_pydantic_dependency(self):
        data = self._load()
        deps = data["project"]["dependencies"]
        assert any("pydantic" in d for d in deps)

    def test_no_amplifier_core_dependency(self):
        data = self._load()
        deps = data["project"]["dependencies"]
        assert not any("amplifier" in d.lower() for d in deps)

    def test_hatchling_build_backend(self):
        data = self._load()
        assert data["build-system"]["build-backend"] == "hatchling.build"

    def test_no_entry_points(self):
        data = self._load()
        assert "entry-points" not in data.get("project", {})
        assert "scripts" not in data.get("project", {})
        assert "gui-scripts" not in data.get("project", {})
