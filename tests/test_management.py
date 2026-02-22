"""Tests for EnvDestroyTool and EnvListTool — environment management tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# Stub backend (mirrors env-common/tests/test_registry.py StubBackend)
# ---------------------------------------------------------------------------


class StubBackend:
    """Minimal backend that tracks cleanup calls and provides configurable info."""

    def __init__(
        self, env_type: str = "local", info_extra: dict[str, Any] | None = None
    ):
        self._env_type = env_type
        self._info_extra = info_extra or {}
        self.cleaned_up = False

    @property
    def env_type(self) -> str:
        return self._env_type

    async def exec_command(
        self, cmd: str, timeout: float | None = None, workdir: str | None = None
    ) -> EnvExecResult:
        return EnvExecResult(stdout="", stderr="", exit_code=0)

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        return ""

    async def write_file(self, path: str, content: str) -> None:
        pass

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        return "ok"

    async def file_exists(self, path: str) -> bool:
        return False

    async def list_dir(self, path: str) -> list[EnvFileEntry]:
        return []

    async def grep(
        self, pattern: str, path: str | None = None, glob_filter: str | None = None
    ) -> str:
        return ""

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        return []

    async def cleanup(self) -> None:
        self.cleaned_up = True

    def info(self) -> dict[str, Any]:
        return {"type": self._env_type, **self._info_extra}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> EnvironmentRegistry:
    return EnvironmentRegistry()


@pytest.fixture
def registry_with_instances(registry: EnvironmentRegistry) -> EnvironmentRegistry:
    """Registry pre-loaded with two stub instances."""
    registry.register(
        "local",
        StubBackend("local", {"working_dir": "/home"}),
        "local",
    )
    registry.register(
        "build",
        StubBackend("docker", {"container_id": "abc"}),
        "docker",
    )
    return registry


# ---------------------------------------------------------------------------
# TestEnvDestroyTool
# ---------------------------------------------------------------------------


class TestEnvDestroyToolName:
    """Tool identity."""

    def test_name_is_env_destroy(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.management import EnvDestroyTool

        tool = EnvDestroyTool(registry)
        assert tool.name == "env_destroy"


class TestEnvDestroyToolExecute:
    """Destroy behaviour."""

    def test_destroy_existing_instance(
        self, registry_with_instances: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.management import EnvDestroyTool

        reg = registry_with_instances
        # Grab reference to the backend before destroying
        backend = reg.get("build")
        assert backend is not None

        tool = EnvDestroyTool(reg)
        result = asyncio.run(tool.execute({"instance": "build"}))

        assert result.success is True
        # Backend cleanup was called
        assert backend.cleaned_up is True
        # Instance removed from registry
        assert reg.get("build") is None

    def test_destroy_missing_returns_error(
        self, registry_with_instances: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.management import EnvDestroyTool

        tool = EnvDestroyTool(registry_with_instances)
        result = asyncio.run(tool.execute({"instance": "nonexistent"}))

        assert result.success is False
        assert "nonexistent" in result.error["message"]
        # Should list active instances to help the user
        assert "local" in result.error["message"]
        assert "build" in result.error["message"]

    def test_destroy_local_allowed(
        self, registry_with_instances: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.management import EnvDestroyTool

        reg = registry_with_instances
        backend = reg.get("local")

        tool = EnvDestroyTool(reg)
        result = asyncio.run(tool.execute({"instance": "local"}))

        assert result.success is True
        assert backend.cleaned_up is True
        assert reg.get("local") is None

    def test_missing_instance_param_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.management import EnvDestroyTool

        tool = EnvDestroyTool(registry)
        result = asyncio.run(tool.execute({}))

        assert result.success is False
        assert "instance" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# TestEnvListTool
# ---------------------------------------------------------------------------


class TestEnvListToolName:
    """Tool identity."""

    def test_name_is_env_list(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.management import EnvListTool

        tool = EnvListTool(registry)
        assert tool.name == "env_list"


class TestEnvListToolExecute:
    """List behaviour."""

    def test_list_empty_registry(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.management import EnvListTool

        tool = EnvListTool(registry)
        result = asyncio.run(tool.execute({}))

        assert result.success is True
        parsed = json.loads(result.output)
        assert parsed == []

    def test_list_returns_all_instances(
        self, registry_with_instances: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.management import EnvListTool

        tool = EnvListTool(registry_with_instances)
        result = asyncio.run(tool.execute({}))

        assert result.success is True
        parsed = json.loads(result.output)
        assert len(parsed) == 2
        names = {entry["name"] for entry in parsed}
        assert names == {"local", "build"}
        types = {entry["type"] for entry in parsed}
        assert types == {"local", "docker"}

    def test_list_no_params_needed(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.management import EnvListTool

        tool = EnvListTool(registry)
        # Should work with empty dict (no parameters required)
        result = asyncio.run(tool.execute({}))
        assert result.success is True
