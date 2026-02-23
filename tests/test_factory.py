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
        # Configurable per-operation overrides: {operation: ToolResult}
        self._operation_results: dict[str, ToolResult] = {}
        # Configurable per-(operation, container) overrides
        self._container_results: dict[tuple[str, str], ToolResult] = {}

    def set_result(self, operation: str, result: ToolResult) -> None:
        """Configure a fixed result for a given operation."""
        self._operation_results[operation] = result

    def set_container_result(
        self, operation: str, container: str, result: ToolResult
    ) -> None:
        """Configure a result for a specific (operation, container) pair."""
        self._container_results[(operation, container)] = result

    async def execute(self, input_dict: dict) -> ToolResult:
        self.calls.append(input_dict)
        op = input_dict.get("operation", "")
        container = input_dict.get("container", "")

        # Check per-(operation, container) override first
        key = (op, container)
        if key in self._container_results:
            return self._container_results[key]

        # Check per-operation override
        if op in self._operation_results:
            return self._operation_results[op]

        if op == "create":
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


# ---------------------------------------------------------------------------
# TestEnvCreateComposeSchema — compose parameter schema checks
# ---------------------------------------------------------------------------


class TestEnvCreateComposeSchema:
    """Verify env_create input_schema includes compose params."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_schema_has_compose_files(self) -> None:
        props = self.tool.input_schema["properties"]
        assert "compose_files" in props
        assert props["compose_files"]["type"] == "array"

    def test_schema_has_compose_project(self) -> None:
        props = self.tool.input_schema["properties"]
        assert "compose_project" in props
        assert props["compose_project"]["type"] == "string"

    def test_schema_has_attach_to(self) -> None:
        props = self.tool.input_schema["properties"]
        assert "attach_to" in props
        assert props["attach_to"]["type"] == "string"

    def test_schema_has_health_check(self) -> None:
        props = self.tool.input_schema["properties"]
        assert "health_check" in props
        assert props["health_check"]["type"] == "boolean"

    def test_schema_has_health_timeout(self) -> None:
        props = self.tool.input_schema["properties"]
        assert "health_timeout" in props
        assert props["health_timeout"]["type"] == "integer"

    def test_compose_params_not_required(self) -> None:
        """All compose params are optional."""
        required = self.tool.input_schema.get("required", [])
        for param in (
            "compose_files",
            "compose_project",
            "attach_to",
            "health_check",
            "health_timeout",
        ):
            assert param not in required


# ---------------------------------------------------------------------------
# TestEnvCreateComposeDocker — compose stack creation in _create_docker()
# ---------------------------------------------------------------------------


class TestEnvCreateComposeDocker:
    """Compose stack creation via _create_docker()."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.containers_tool = MockContainersTool()
        self.coordinator.register_tool("containers", self.containers_tool)
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_compose_calls_containers_with_compose_content(self, tmp_path: Any) -> None:
        """When compose_files provided, containers tool gets compose_content."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("services:\n  web:\n    image: nginx\n")

        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_files": [str(compose_file)],
                    "compose_project": "myproj",
                }
            )
        )

        assert result.success is True
        assert len(self.containers_tool.calls) == 1
        call = self.containers_tool.calls[0]
        assert call["operation"] == "create"
        assert "compose_content" in call
        assert call["compose_content"] is not None
        assert "nginx" in call["compose_content"]
        assert call.get("compose_project") == "myproj"

    def test_compose_resolves_service_name(self) -> None:
        """When attach_to + compose_project set, container_id = {project}-{service}-1."""
        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_project": "myproj",
                    "attach_to": "web",
                }
            )
        )

        assert result.success is True
        backend = self.registry.get("mystack")
        assert isinstance(backend, DockerBackend)
        assert backend._container_id == "myproj-web-1"

    def test_compose_without_attach_to_uses_output(self) -> None:
        """When no attach_to, use container from create output."""
        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_project": "myproj",
                }
            )
        )

        assert result.success is True
        backend = self.registry.get("mystack")
        assert isinstance(backend, DockerBackend)
        # MockContainersTool returns "ctr-123" as container_id
        assert backend._container_id == "ctr-123"

    def test_non_compose_path_unchanged(self) -> None:
        """Standard Docker create (no compose params) still works as before."""
        result = asyncio.run(self.tool.execute({"type": "docker", "name": "build"}))

        assert result.success is True
        backend = self.registry.get("build")
        assert isinstance(backend, DockerBackend)

        call = self.containers_tool.calls[0]
        assert call["operation"] == "create"
        assert call.get("purpose") == "python"
        assert "compose_content" not in call
        assert "compose_project" not in call


# ---------------------------------------------------------------------------
# TestEnvCreateComposeServiceResolution — A.4: service name verification
# ---------------------------------------------------------------------------


class TestEnvCreateComposeServiceResolution:
    """Service name resolution verifies container exists via status call."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.containers_tool = MockContainersTool()
        self.coordinator.register_tool("containers", self.containers_tool)
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_compose_attach_to_resolves_with_status_check(self) -> None:
        """When attach_to + compose_project set, factory checks resolved container via status."""
        # Status call for "myproj-web-1" succeeds → use resolved name
        self.containers_tool.set_container_result(
            "status",
            "myproj-web-1",
            ToolResult(success=True, output={"status": "running"}),
        )

        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_project": "myproj",
                    "attach_to": "web",
                }
            )
        )

        assert result.success is True
        backend = self.registry.get("mystack")
        assert isinstance(backend, DockerBackend)
        assert backend._container_id == "myproj-web-1"

        # Verify a status call was made for the resolved name
        status_calls = [
            c for c in self.containers_tool.calls if c.get("operation") == "status"
        ]
        assert len(status_calls) == 1
        assert status_calls[0]["container"] == "myproj-web-1"

    def test_compose_attach_to_fallback_to_literal(self) -> None:
        """When resolved service name doesn't exist (status fails), fall back to literal."""
        # Status call for "myproj-mydb-1" fails → fall back to "mydb" as literal
        self.containers_tool.set_container_result(
            "status",
            "myproj-mydb-1",
            ToolResult(success=False, error={"message": "No such container"}),
        )

        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_project": "myproj",
                    "attach_to": "mydb",
                }
            )
        )

        assert result.success is True
        backend = self.registry.get("mystack")
        assert isinstance(backend, DockerBackend)
        # Falls back to the literal attach_to value
        assert backend._container_id == "mydb"


# ---------------------------------------------------------------------------
# TestEnvCreateComposeHealthCheck — A.5: health check waiting
# ---------------------------------------------------------------------------


class TestEnvCreateComposeHealthCheck:
    """Health check waiting for compose environments."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.containers_tool = MockContainersTool()
        self.coordinator.register_tool("containers", self.containers_tool)
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_compose_health_check_waits(self) -> None:
        """When health_check=true, factory calls wait_healthy on the containers tool."""
        self.containers_tool.set_result(
            "wait_healthy", ToolResult(success=True, output={"status": "healthy"})
        )

        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_project": "myproj",
                    "health_check": True,
                }
            )
        )

        assert result.success is True
        wait_calls = [
            c
            for c in self.containers_tool.calls
            if c.get("operation") == "wait_healthy"
        ]
        assert len(wait_calls) == 1
        # Default timeout is 60s, interval 2s → retries = 30
        assert wait_calls[0]["retries"] == 30
        assert wait_calls[0]["interval"] == 2

    def test_compose_health_check_timeout(self) -> None:
        """When health check fails, raises RuntimeError with timeout info."""
        self.containers_tool.set_result(
            "wait_healthy",
            ToolResult(success=False, error={"message": "Timed out"}),
        )

        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_project": "myproj",
                    "health_check": True,
                    "health_timeout": 30,
                }
            )
        )

        # The RuntimeError is caught by execute() and returned as error
        assert result.success is False
        assert result.error is not None
        assert "health check failed" in result.error["message"].lower()
        assert "30" in result.error["message"]

    def test_compose_no_health_check_by_default(self) -> None:
        """When health_check not set, no wait_healthy call is made."""
        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "docker",
                    "name": "mystack",
                    "compose_project": "myproj",
                }
            )
        )

        assert result.success is True
        wait_calls = [
            c
            for c in self.containers_tool.calls
            if c.get("operation") == "wait_healthy"
        ]
        assert len(wait_calls) == 0


# ---------------------------------------------------------------------------
# B.2: env_create returns structured dict (not string)
# ---------------------------------------------------------------------------


class TestEnvCreateReturnsDict:
    """env_create output is a dict with connection details."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.containers_tool = MockContainersTool()
        self.coordinator.register_tool("containers", self.containers_tool)
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_create_local_returns_dict(self) -> None:
        """Local create returns dict with instance, type, working_dir."""
        result = asyncio.run(
            self.tool.execute(
                {"type": "local", "name": "mylocal", "working_dir": "/tmp"}
            )
        )
        assert result.success is True
        out = result.output
        assert isinstance(out, dict)
        assert out["instance"] == "mylocal"
        assert out["type"] == "local"
        assert out["working_dir"] == "/tmp"

    def test_create_docker_returns_dict(self) -> None:
        """Docker create returns dict with instance, type, container_id."""
        result = asyncio.run(self.tool.execute({"type": "docker", "name": "build"}))
        assert result.success is True
        out = result.output
        assert isinstance(out, dict)
        assert out["instance"] == "build"
        assert out["type"] == "docker"
        assert out["container_id"] == "ctr-123"

    def test_create_ssh_returns_dict(self) -> None:
        """SSH create returns dict with instance, type, host."""
        result = asyncio.run(
            self.tool.execute(
                {
                    "type": "ssh",
                    "name": "pi",
                    "host": "voicebox",
                    "username": "admin",
                    "_test_exec_fn": fake_ssh_exec,
                    "_test_disconnect_fn": fake_ssh_disconnect,
                }
            )
        )
        assert result.success is True
        out = result.output
        assert isinstance(out, dict)
        assert out["instance"] == "pi"
        assert out["type"] == "ssh"
        assert out["host"] == "voicebox"
        assert out["username"] == "admin"


# ---------------------------------------------------------------------------
# B.3: attach_to without compose wraps existing container
# ---------------------------------------------------------------------------


class TestEnvCreateAttachToDocker:
    """attach_to without compose params wraps an existing container."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.containers_tool = MockContainersTool()
        self.coordinator.register_tool("containers", self.containers_tool)
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_attach_to_docker_skips_creation(self) -> None:
        """When attach_to set without compose, no 'create' call to containers tool."""
        # Status check succeeds
        self.containers_tool.set_container_result(
            "status",
            "existing-ctr",
            ToolResult(success=True, output={"status": "running"}),
        )

        result = asyncio.run(
            self.tool.execute(
                {"type": "docker", "name": "attached", "attach_to": "existing-ctr"}
            )
        )

        assert result.success is True
        create_calls = [
            c for c in self.containers_tool.calls if c.get("operation") == "create"
        ]
        assert len(create_calls) == 0, "Should not call 'create' when attaching"

    def test_attach_to_docker_verifies_container_exists(self) -> None:
        """Factory calls status on the container to verify it exists."""
        self.containers_tool.set_container_result(
            "status",
            "my-ctr",
            ToolResult(success=True, output={"status": "running"}),
        )

        asyncio.run(
            self.tool.execute({"type": "docker", "name": "att", "attach_to": "my-ctr"})
        )

        status_calls = [
            c for c in self.containers_tool.calls if c.get("operation") == "status"
        ]
        assert len(status_calls) == 1
        assert status_calls[0]["container"] == "my-ctr"

    def test_attach_to_docker_fails_if_container_not_found(self) -> None:
        """If attach_to container doesn't exist, return error."""
        self.containers_tool.set_container_result(
            "status",
            "ghost",
            ToolResult(success=False, error={"message": "No such container"}),
        )

        result = asyncio.run(
            self.tool.execute({"type": "docker", "name": "att", "attach_to": "ghost"})
        )

        assert result.success is False
        assert result.error is not None
        assert "ghost" in result.error["message"]

    def test_attach_to_docker_creates_docker_backend(self) -> None:
        """Attached backend is a DockerBackend with correct container_id."""
        self.containers_tool.set_container_result(
            "status",
            "my-ctr",
            ToolResult(success=True, output={"status": "running"}),
        )

        asyncio.run(
            self.tool.execute({"type": "docker", "name": "att", "attach_to": "my-ctr"})
        )

        backend = self.registry.get("att")
        assert isinstance(backend, DockerBackend)
        assert backend._container_id == "my-ctr"


# ---------------------------------------------------------------------------
# B.4: owned flag wiring (create=True, attach=False)
# ---------------------------------------------------------------------------


class TestEnvCreateOwnedFlag:
    """owned=True for create, owned=False for attach_to."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.containers_tool = MockContainersTool()
        self.coordinator.register_tool("containers", self.containers_tool)
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_create_sets_owned_true(self) -> None:
        """Normal create registers with owned=True."""
        asyncio.run(self.tool.execute({"type": "local", "name": "mylocal"}))

        instances = self.registry.list_instances()
        inst = [i for i in instances if i["name"] == "mylocal"][0]
        assert inst["owned"] is True

    def test_attach_sets_owned_false(self) -> None:
        """attach_to registers with owned=False."""
        self.containers_tool.set_container_result(
            "status",
            "ext-ctr",
            ToolResult(success=True, output={"status": "running"}),
        )

        asyncio.run(
            self.tool.execute({"type": "docker", "name": "att", "attach_to": "ext-ctr"})
        )

        instances = self.registry.list_instances()
        inst = [i for i in instances if i["name"] == "att"][0]
        assert inst["owned"] is False

    def test_docker_create_sets_owned_true(self) -> None:
        """Normal Docker create (no attach_to) registers with owned=True."""
        asyncio.run(self.tool.execute({"type": "docker", "name": "build"}))

        instances = self.registry.list_instances()
        inst = [i for i in instances if i["name"] == "build"][0]
        assert inst["owned"] is True


# ---------------------------------------------------------------------------
# C.3: SSH discovery wiring in factory._create_ssh()
# ---------------------------------------------------------------------------


class TestEnvCreateSSHDiscovery:
    """Factory wires SSH credential auto-discovery into _create_ssh()."""

    def setup_method(self) -> None:
        self.registry = EnvironmentRegistry()
        self.coordinator = MockCoordinator()
        self.tool = EnvCreateTool(registry=self.registry, coordinator=self.coordinator)

    def test_ssh_create_uses_discovery(self) -> None:
        """When only host provided, factory discovers username and key_file."""
        discovered = {
            "username": "discovered_user",
            "key_file": "/home/user/.ssh/id_ed25519",
            "resolved_host": "10.0.0.1",
        }

        from unittest.mock import patch

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.discover_ssh_config",
            return_value=discovered,
        ):
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
        out = result.output
        assert isinstance(out, dict)
        # Output should reflect discovered values
        assert out["host"] == "voicebox"
        assert out["username"] == "discovered_user"

    def test_ssh_explicit_overrides_discovery(self) -> None:
        """When username explicitly provided, it overrides discovered."""
        discovered = {
            "username": "discovered_user",
            "key_file": "/home/user/.ssh/id_ed25519",
        }

        from unittest.mock import patch

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.discover_ssh_config",
            return_value=discovered,
        ):
            result = asyncio.run(
                self.tool.execute(
                    {
                        "type": "ssh",
                        "name": "pi",
                        "host": "voicebox",
                        "username": "explicit_user",
                        "_test_exec_fn": fake_ssh_exec,
                        "_test_disconnect_fn": fake_ssh_disconnect,
                    }
                )
            )

        assert result.success is True
        out = result.output
        assert isinstance(out, dict)
        # Explicit username wins over discovered
        assert out["username"] == "explicit_user"

    def test_ssh_output_reflects_resolved_host(self) -> None:
        """Output host stays as user-provided; resolved_host used internally."""
        discovered = {
            "username": "admin",
            "resolved_host": "192.168.1.50",
        }

        from unittest.mock import patch

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.discover_ssh_config",
            return_value=discovered,
        ):
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
        out = result.output
        assert isinstance(out, dict)
        # Output should show original host for user display
        assert out["host"] == "voicebox"

    def test_ssh_discovery_called_with_host(self) -> None:
        """Factory calls discover_ssh_config with the host parameter."""
        from unittest.mock import patch

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.discover_ssh_config",
            return_value={"username": "testuser"},
        ) as mock_discover:
            asyncio.run(
                self.tool.execute(
                    {
                        "type": "ssh",
                        "name": "pi",
                        "host": "myhost.local",
                        "_test_exec_fn": fake_ssh_exec,
                        "_test_disconnect_fn": fake_ssh_disconnect,
                    }
                )
            )

        mock_discover.assert_called_once_with("myhost.local")
