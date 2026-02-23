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
                "compose_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Docker: compose file paths to bring up a multi-service stack",
                },
                "compose_project": {
                    "type": "string",
                    "description": "Docker: compose project name for namespace isolation and teardown",
                },
                "attach_to": {
                    "type": "string",
                    "description": (
                        "Docker: service name (with compose) or container ID (without compose) "
                        "to attach to instead of creating a new container"
                    ),
                },
                "health_check": {
                    "type": "boolean",
                    "description": "Docker: wait for target container to be healthy before returning (default: false)",
                },
                "health_timeout": {
                    "type": "integer",
                    "description": "Docker: seconds to wait for health check (default: 60)",
                },
                "env_policy": {
                    "type": "string",
                    "enum": ["inherit_all", "core_only", "inherit_none"],
                    "description": "Environment variable inheritance policy (default: core_only). Controls which host vars are visible to commands.",
                },
                "wrappers": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["logging", "readonly"]},
                    "description": "Composable wrappers to apply (e.g., ['logging', 'readonly'])",
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

            # C.2 + D.2: Apply composable wrappers
            # Order matters: ReadOnly innermost, Logging outermost
            wrappers = input.get("wrappers", [])
            if "readonly" in wrappers:
                from amplifier_env_common.wrappers.readonly_wrapper import (
                    ReadOnlyWrapper,
                )

                backend = ReadOnlyWrapper(inner=backend)
            if "logging" in wrappers:
                from amplifier_env_common.wrappers.logging_wrapper import (
                    LoggingWrapper,
                )

                backend = LoggingWrapper(inner=backend)

            # B.4: Determine ownership — attached resources are not owned
            is_attached = bool(input.get("attach_to"))
            owned = not is_attached

            env_policy = input.get("env_policy", "core_only")
            metadata = {
                "persistent": input.get("persistent", False),
                "env_policy": env_policy,
            }
            self._registry.register(
                env_name, backend, env_type, metadata=metadata, owned=owned
            )

            # B.2: Return structured dict with connection details
            output_dict: dict[str, Any] = {
                "instance": env_name,
                "type": env_type,
            }
            if env_type == "local":
                output_dict["working_dir"] = getattr(backend, "_working_dir", None)
            elif env_type == "docker":
                output_dict["container_id"] = getattr(backend, "_container_id", None)
                output_dict["working_dir"] = getattr(backend, "_working_dir", None)
                compose_proj = getattr(backend, "_compose_project", None)
                if compose_proj:
                    output_dict["compose_project"] = compose_proj
            elif env_type == "ssh":
                output_dict["host"] = input.get("host")
                output_dict["username"] = input.get("_resolved_username")
                output_dict["port"] = input.get("_resolved_port", 22)

            return ToolResult(success=True, output=output_dict)
        except Exception as e:
            logger.warning("env_create failed for '%s': %s", env_name, e)
            return ToolResult(success=False, error={"message": str(e)})

    async def _create_local(self, input: dict) -> LocalBackend:
        working_dir = input.get("working_dir", os.getcwd())
        env_policy = input.get("env_policy", "core_only")
        return LocalBackend(working_dir=working_dir, env_policy=env_policy)

    async def _create_docker(self, input: dict) -> Any:
        from amplifier_env_common.backends.docker import DockerBackend

        containers_tool = self._coordinator.get("tools", "containers")
        if containers_tool is None:
            raise RuntimeError(
                "Docker environments require the 'containers' tool. "
                "Ensure the containers bundle is loaded."
            )

        compose_files = input.get("compose_files")
        compose_project = input.get("compose_project")
        attach_to = input.get("attach_to")

        if compose_files or compose_project:
            return await self._create_docker_compose(
                input, containers_tool, compose_files, compose_project, attach_to
            )

        # B.3: attach_to without compose — wrap existing container
        if attach_to:
            status_result = await containers_tool.execute(
                {"operation": "status", "container": attach_to}
            )
            if not status_result.success:
                raise RuntimeError(f"Container '{attach_to}' not found or not running")
            return DockerBackend(
                containers_invoke=containers_tool.execute,
                container_id=attach_to,
            )

        # NON-COMPOSE PATH: existing behavior (create a single container)
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

    async def _create_docker_compose(
        self,
        input: dict,
        containers_tool: Any,
        compose_files: list[str] | None,
        compose_project: str | None,
        attach_to: str | None,
    ) -> Any:
        """Bring up a compose stack, then attach to a service container."""
        from amplifier_env_common.backends.docker import DockerBackend

        # Read and merge compose files into a single YAML string
        compose_content = None
        if compose_files:
            import yaml

            merged: dict[str, Any] = {}
            for filepath in compose_files:
                with open(filepath) as fh:
                    content = yaml.safe_load(fh)
                    if content:
                        for key, val in content.items():
                            if key == "services" and "services" in merged:
                                merged["services"].update(val)
                            else:
                                merged[key] = val
            compose_content = yaml.dump(merged)

        # Bring up the stack via containers tool
        create_params: dict[str, Any] = {
            "operation": "create",
            "name": input.get("name"),
        }
        if compose_content is not None:
            create_params["compose_content"] = compose_content
        if compose_project is not None:
            create_params["compose_project"] = compose_project

        create_result = await containers_tool.execute(create_params)

        if not create_result.success:
            error_msg = "Compose stack creation failed"
            if create_result.error:
                error_msg = create_result.error.get("message", error_msg)
            raise RuntimeError(f"Failed to create compose stack: {error_msg}")

        # Resolve the container to attach to
        if attach_to:
            if compose_project:
                # Try service name resolution: {project}-{service}-1
                resolved = f"{compose_project}-{attach_to}-1"
                # Verify it exists by calling containers tool status
                status_result = await containers_tool.execute(
                    {"operation": "status", "container": resolved}
                )
                if status_result.success:
                    container_id = resolved
                else:
                    # Fall back to using attach_to as a literal container ID/name
                    container_id = attach_to
            else:
                container_id = attach_to
        else:
            output = create_result.output
            if isinstance(output, dict):
                container_id = (
                    output.get("container") or output.get("container_id") or ""
                )
            else:
                container_id = str(output) if output else ""

            if not container_id:
                container_id = input.get("name", "")

        if not container_id:
            raise RuntimeError(
                "Compose stack created but could not resolve a container to attach to"
            )

        # Health check waiting
        if input.get("health_check"):
            timeout = input.get("health_timeout", 60)
            health_result = await containers_tool.execute(
                {
                    "operation": "wait_healthy",
                    "container": container_id,
                    "health_command": "true",
                    "retries": timeout // 2,
                    "interval": 2,
                }
            )
            if not health_result.success:
                raise RuntimeError(
                    f"Health check failed for container '{container_id}' after {timeout}s"
                )

        return DockerBackend(
            containers_invoke=containers_tool.execute, container_id=container_id
        )

    async def _create_ssh(self, input: dict) -> Any:
        from amplifier_env_common.backends.ssh import SSHBackendWrapper

        from .ssh_discovery import discover_ssh_config

        host = input.get("host")
        if not host:
            raise ValueError(
                "SSH environments require 'host' parameter. "
                "Example: env_create(type='ssh', name='pi', host='voicebox')"
            )

        # Auto-discover credentials (explicit params override)
        discovered = discover_ssh_config(host)

        # Merge: explicit params always win over discovered
        username = input.get("username") or discovered.get("username")
        key_file = input.get("key_file") or discovered.get("key_file")
        port = input.get("port") or discovered.get("port")
        resolved_host = discovered.get("resolved_host", host)

        # Stash resolved values for output dict (see execute())
        input["_resolved_username"] = username
        input["_resolved_port"] = port or 22

        # Support test injection of exec_fn/disconnect_fn for unit testing
        test_exec_fn = input.get("_test_exec_fn")
        if test_exec_fn is not None:
            return SSHBackendWrapper(
                exec_fn=test_exec_fn,
                host=resolved_host,
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
                host=resolved_host,
                username=username,
                key_file=key_file,
                known_hosts=None,
            )
            async_backend = AsyncSSHBackend(config=config)
            connection = SSHConnection(config=config, backend=async_backend)
            await connection.connect()

            return SSHBackendWrapper(
                exec_fn=connection.exec_command,
                host=resolved_host,
                disconnect_fn=connection.disconnect,
            )
        except ImportError:
            raise RuntimeError(
                "SSH environments require 'asyncssh'. Install: uv pip install asyncssh"
            )
