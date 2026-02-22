"""env_create — factory tool for creating environment instances on demand."""

from __future__ import annotations

import logging
import os
from typing import Any

from amplifier_core import ToolResult

from amplifier_env_common.backends.local import LocalBackend
from amplifier_env_common.registry import EnvironmentRegistry

logger = logging.getLogger(__name__)


class EnvCreateTool:
    """Factory tool: creates named environment instances on demand."""

    def __init__(self, registry: EnvironmentRegistry, coordinator: Any) -> None:
        self._registry = registry
        self._coordinator = coordinator

    @property
    def name(self) -> str:
        return "env_create"

    @property
    def description(self) -> str:
        return (
            "Create a new execution environment instance. "
            "Types: 'local' (host filesystem), 'docker' (container), 'ssh' (remote host). "
            "Returns the instance name for use with other env_* tools."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["local", "docker", "ssh"],
                    "description": "Environment type to create",
                },
                "name": {
                    "type": "string",
                    "description": "Instance name (you choose — e.g., 'build-server', 'pi')",
                },
                "purpose": {
                    "type": "string",
                    "description": "Docker: container purpose/base image (default: 'python')",
                },
                "host": {
                    "type": "string",
                    "description": "SSH: hostname or IP (required for ssh type)",
                },
                "username": {
                    "type": "string",
                    "description": "SSH: username (optional)",
                },
                "key_file": {
                    "type": "string",
                    "description": "SSH: path to private key (optional)",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Local: base directory for operations (default: cwd)",
                },
            },
            "required": ["type", "name"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        env_type = input.get("type")
        env_name = input.get("name")

        if not env_type:
            return ToolResult(
                success=False, error={"message": "Missing required parameter: 'type'"}
            )
        if not env_name:
            return ToolResult(
                success=False, error={"message": "Missing required parameter: 'name'"}
            )

        # Check for duplicate
        if self._registry.get(env_name) is not None:
            existing = [i["name"] for i in self._registry.list_instances()]
            return ToolResult(
                success=False,
                error={
                    "message": f"Instance '{env_name}' already exists. Active: {existing}"
                },
            )

        try:
            if env_type == "local":
                backend = await self._create_local(input)
            elif env_type == "docker":
                backend = await self._create_docker(input)
            elif env_type == "ssh":
                backend = await self._create_ssh(input)
            else:
                return ToolResult(
                    success=False,
                    error={
                        "message": f"Unknown environment type: '{env_type}'. Use: local, docker, ssh"
                    },
                )

            metadata = {"persistent": input.get("persistent", False)}
            self._registry.register(env_name, backend, env_type, metadata=metadata)

            return ToolResult(
                success=True,
                output=f"Created {env_type} environment '{env_name}'. "
                f"Use instance='{env_name}' in env_* tools.",
            )
        except Exception as e:
            logger.warning("env_create failed for '%s': %s", env_name, e)
            return ToolResult(success=False, error={"message": str(e)})

    async def _create_local(self, input: dict) -> LocalBackend:
        working_dir = input.get("working_dir", os.getcwd())
        return LocalBackend(working_dir=working_dir)

    async def _create_docker(self, input: dict) -> Any:
        from amplifier_env_common.backends.docker import DockerBackend

        containers_tool = self._coordinator.get("tools", "containers")
        if containers_tool is None:
            raise RuntimeError(
                "Docker environments require the 'containers' tool. "
                "Ensure the containers bundle is loaded."
            )

        purpose = input.get("purpose", "python")
        create_result = await containers_tool.execute(
            {"operation": "create", "purpose": purpose, "name": input.get("name")}
        )

        if not create_result.success:
            error_msg = "Container creation failed"
            if create_result.error:
                error_msg = create_result.error.get("message", error_msg)
            raise RuntimeError(f"Failed to create container: {error_msg}")

        output = create_result.output
        if isinstance(output, dict):
            container_id = output.get("container") or output.get("container_id") or ""
        else:
            container_id = str(output) if output else ""

        if not container_id:
            raise RuntimeError(
                "Container creation succeeded but returned no container ID"
            )

        return DockerBackend(
            containers_invoke=containers_tool.execute, container_id=container_id
        )

    async def _create_ssh(self, input: dict) -> Any:
        from amplifier_env_common.backends.ssh import SSHBackendWrapper

        host = input.get("host")
        if not host:
            raise ValueError(
                "SSH environments require 'host' parameter. "
                "Example: env_create(type='ssh', name='pi', host='voicebox')"
            )

        # Support test injection of exec_fn/disconnect_fn for unit testing
        test_exec_fn = input.get("_test_exec_fn")
        if test_exec_fn is not None:
            return SSHBackendWrapper(
                exec_fn=test_exec_fn,
                host=host,
                disconnect_fn=input.get("_test_disconnect_fn"),
            )

        # Real SSH connection path
        try:
            from amplifier_module_tools_env_ssh.async_backend import AsyncSSHBackend
            from amplifier_module_tools_env_ssh.connection import (
                SSHConnection,
                SSHConnectionConfig,
            )

            config = SSHConnectionConfig(
                host=host,
                username=input.get("username"),
                key_file=input.get("key_file"),
                known_hosts=None,
            )
            async_backend = AsyncSSHBackend(config=config)
            connection = SSHConnection(config=config, backend=async_backend)
            await connection.connect()

            return SSHBackendWrapper(
                exec_fn=connection.exec_command,
                host=host,
                disconnect_fn=connection.disconnect,
            )
        except ImportError:
            raise RuntimeError(
                "SSH environments require 'asyncssh'. Install: uv pip install asyncssh"
            )
