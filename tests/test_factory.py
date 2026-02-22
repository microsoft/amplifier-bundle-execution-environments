"""Tests for EnvCreateTool — factory tool for creating environment instances."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from amplifier_core import ToolResult
from amplifier_env_common.backends.docker import DockerBackend
from amplifier_env_common.backends.local import LocalBackend
from amplifier_env_common.backends.ssh import SSHBackendWrapper
from amplifier_env_common.registry import EnvironmentRegistry

from amplifier_module_tools_env_all.factory import EnvCreateTool


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class MockCoordinator:
    """Minimal coordinator stub that holds tools by name."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Any] = {}
        self._tools: dict[str, Any] = {}

    def register_tool(self, name: str, tool: Any) -> None:
        self._tools[name] = tool

    def get(self, kind: str, name: str) -> Any:
        return self._tools.get(name)

    def register_capability(self, name: str, value: Any) -> None:
        self._capabilities[name] = value

    def get_capability(self, name: str) -> Any:
        return self._capabilities.get(name)


class MockContainersTool:
    """Simulates the containers tool for Docker backend creation."""

    def __init__(self, container_id: str = "ctr-123") -> None:
        self._container_id = container_id
        self.calls: list[dict] = []

    async def execute(self, input_dict: dict) -> ToolResult:
        self.calls.append(input_dict)
        if input_dict.get("operation") == "create":
            return ToolResult(
                success=True,
                output={
                    "container": self._container_id,
                    "container_id": self._container_id,
                },
            )
        return ToolResult(success=True, output={})


@dataclass
class FakeSSHExecResult:
    """Fake result from SSH exec_fn."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


async def fake_ssh_exec(cmd: str, timeout: float | None = None) -> FakeSSHExecResult:
    """Fake SSH exec function."""
    return FakeSSHExecResult()


async def fake_ssh_disconnect() -> None:
    """Fake SSH disconnect function."""


# ---------------------------------------------------------------------------
# TestEnvCreateToolProtocol — structural checks
# ---------------------------------------------------------------------------


class TestEnvCreateToolProtocol:
    """Tool protocol: name, description, input_schema, execute."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_satisfies_tool_protocol(self) -> None:
        """Has name, description, input_schema, execute."""
        assert hasattr(self.tool, "name")
        assert hasattr(self.tool, "description")
        assert hasattr(self.tool, "input_schema")
        assert hasattr(self.tool, "execute")
        assert callable(self.tool.execute)

    def test_name_is_env_create(self) -> None:
        assert self.tool.name == "env_create"

    def test_description_is_nonempty(self) -> None:
        assert isinstance(self.tool.description, str)
        assert len(self.tool.description) > 10

    def test_input_schema_has_type_and_name_required(self) -> None:
        schema = self.tool.input_schema
        assert schema["type"] == "object"
        assert "type" in schema["properties"]
        assert "name" in schema["properties"]
        assert "type" in schema["required"]
        assert "name" in schema["required"]


# ---------------------------------------------------------------------------
# TestEnvCreateLocal — local backend creation
# ---------------------------------------------------------------------------


class TestEnvCreateLocal:
    """Creating local environment instances."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_create_local_instance(self) -> None:
        result = asyncio.run(self.tool.execute({"type": "local", "name": "test-local"}))
        assert result.success is True
        backend = self.registry.get("test-local")
        assert backend is not None
        assert isinstance(backend, LocalBackend)

    def test_create_local_with_working_dir(self) -> None:
        result = asyncio.run(
            self.tool.execute({"type": "local", "name": "proj", "working_dir": "/tmp"})
        )
        assert result.success is True
        backend = self.registry.get("proj")
        assert isinstance(backend, LocalBackend)


# ---------------------------------------------------------------------------
# TestEnvCreateDocker — docker backend creation
# ---------------------------------------------------------------------------


class TestEnvCreateDocker:
    """Creating docker environment instances."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.containers_tool = MockContainersTool()
        self.coordinator.register_tool("containers", self.containers_tool)
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_create_docker_instance(self) -> None:
        result = asyncio.run(self.tool.execute({"type": "docker", "name": "build"}))
        assert result.success is True
        backend = self.registry.get("build")
        assert backend is not None
        assert isinstance(backend, DockerBackend)

    def test_docker_calls_containers_tool_create(self) -> None:
        asyncio.run(self.tool.execute({"type": "docker", "name": "ci"}))
        assert len(self.containers_tool.calls) == 1
        call = self.containers_tool.calls[0]
        assert call["operation"] == "create"
        assert call["name"] == "ci"

    def test_docker_without_containers_tool_returns_error(self) -> None:
        """If containers tool is not registered, return error."""
        empty_coord = MockCoordinator()
        tool = EnvCreateTool(registry=self.registry, coordinator=empty_coord)
        result = asyncio.run(tool.execute({"type": "docker", "name": "build"}))
        assert result.success is False
        assert "containers" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# TestEnvCreateSSH — ssh backend creation
# ---------------------------------------------------------------------------


class TestEnvCreateSSH:
    """Creating SSH environment instances (with mocked connection)."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_create_ssh_instance(self) -> None:
        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "ssh",
                    "name": "pi",
                    "host": "voicebox",
                    "_test_exec_fn": fake_ssh_exec,
                    "_test_disconnect_fn": fake_ssh_disconnect,
                }
            )
        )
        assert result.success is True
        backend = self.registry.get("pi")
        assert backend is not None
        assert isinstance(backend, SSHBackendWrapper)

    def test_ssh_missing_host_returns_error(self) -> None:
        result = asyncio.run(self.tool.execute({"type": "ssh", "name": "pi"}))
        assert result.success is False
        assert "host" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# TestEnvCreateErrors — error handling
# ---------------------------------------------------------------------------


class TestEnvCreateErrors:
    """Error cases for env_create."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_missing_type_returns_error(self) -> None:
        result = asyncio.run(self.tool.execute({"name": "test"}))
        assert result.success is False
        assert "type" in result.error["message"].lower()

    def test_missing_name_returns_error(self) -> None:
        result = asyncio.run(self.tool.execute({"type": "local"}))
        assert result.success is False
        assert "name" in result.error["message"].lower()

    def test_duplicate_name_returns_error(self) -> None:
        asyncio.run(self.tool.execute({"type": "local", "name": "dev"}))
        result = asyncio.run(self.tool.execute({"type": "local", "name": "dev"}))
        assert result.success is False
        assert "already exists" in result.error["message"].lower()

    def test_unknown_type_returns_error(self) -> None:
        result = asyncio.run(self.tool.execute({"type": "banana", "name": "test"}))
        assert result.success is False
        assert "unknown" in result.error["message"].lower()

    def test_instance_appears_in_registry(self) -> None:
        """After create, registry.get(name) returns a backend."""
        asyncio.run(self.tool.execute({"type": "local", "name": "visible"}))
        assert self.registry.get("visible") is not None
