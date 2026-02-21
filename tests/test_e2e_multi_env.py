"""End-to-end multi-environment integration test.

Validates that local, Docker, and SSH environment tools can coexist and
work together in a single workflow — with Logging decorators wrapping all
three environments simultaneously.

All backends are mocked (no real Docker daemon or SSH server needed):
- Local: uses tmp_path directly
- Docker: MockContainerExecutor runs shell commands in a temp directory
- SSH: MockSSHBackend uses a local filesystem root

Run with:
    PYTHONPATH=env-local/modules/tools-env-local:\
env-docker/modules/tools-env-docker:env-docker/modules/hooks-env-docker:\
env-ssh/modules/tools-env-ssh:env-ssh/modules/hooks-env-ssh:\
env-decorators/modules/hooks-env-decorators \
    python3 -m pytest env-all/tests/test_e2e_multi_env.py -v
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

# Local environment tools
from amplifier_module_tools_env_local.tools import EnvReadFile as EnvLocalReadFile

# Docker environment tools + mock
from amplifier_module_tools_env_docker.tools import (
    EnvDockerExec,
    EnvDockerWriteFile,
)

# SSH environment tools + mock
from amplifier_module_tools_env_ssh.connection import (
    MockSSHBackend,
    SSHConnection,
    SSHConnectionConfig,
)
from amplifier_module_tools_env_ssh.tools import (
    EnvSSHFileExists,
    EnvSSHWriteFile,
)

# Decorator
from amplifier_module_hooks_env_decorators.logging_decorator import LoggingDecorator


# ---------------------------------------------------------------------------
# Mock container executor (same pattern as env-docker tests)
# ---------------------------------------------------------------------------


@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class MockContainerExecutor:
    """Runs shell commands locally via asyncio subprocess."""

    def __init__(self, working_dir: str) -> None:
        self._working_dir = working_dir

    async def __call__(
        self,
        command: str,
        timeout: int | None = None,
        workdir: str | None = None,
    ) -> ExecResult:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._working_dir,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        return ExecResult(
            stdout=stdout_bytes.decode() if stdout_bytes else "",
            stderr=stderr_bytes.decode() if stderr_bytes else "",
            exit_code=proc.returncode or 0,
        )


# ---------------------------------------------------------------------------
# Helper — simulate tool call lifecycle with decorator hooks
# ---------------------------------------------------------------------------


async def simulate_tool_call_with_decorators(
    decorators: list,
    tool: Any,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """Simulate a full tool call lifecycle with decorator hooks.

    1. Run all pre hooks — if any deny, return the denied result
    2. Execute the tool
    3. Run all post hooks
    4. Return the tool result as a dict
    """
    tool_name = tool.name
    pre_data = {"tool_name": tool_name, "tool_input": tool_input}

    # Pre hooks
    denied_reason = None
    for decorator in decorators:
        result = await decorator.handle_tool_pre("tool:pre", pre_data)
        if result.action == "deny":
            denied_reason = result.reason
            break

    if denied_reason:
        tool_result = {
            "success": False,
            "error": {"error_code": "denied", "message": denied_reason},
        }
    else:
        # Execute the actual tool
        tr = await tool.execute(tool_input)
        tool_result = {
            "success": tr.success,
            "output": tr.output,
        }
        if tr.error:
            tool_result["error"] = tr.error

    # Post hooks
    post_data = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_result": tool_result,
    }
    for decorator in decorators:
        await decorator.handle_tool_post("tool:post", post_data)

    return tool_result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def local_dir(tmp_path: Path) -> Path:
    """Local environment working directory with a config file."""
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / "config.yaml").write_text(
        "app:\n  name: my-app\n  version: 2.0\n"
    )
    return tmp_path / "local"


@pytest.fixture
def docker_dir(tmp_path: Path) -> Path:
    """Docker environment working directory (simulated container filesystem)."""
    (tmp_path / "docker").mkdir()
    return tmp_path / "docker"


@pytest.fixture
def ssh_dir(tmp_path: Path) -> Path:
    """SSH environment root directory (simulated remote filesystem)."""
    (tmp_path / "ssh").mkdir()
    return tmp_path / "ssh"


@pytest.fixture
def docker_executor(docker_dir: Path) -> MockContainerExecutor:
    return MockContainerExecutor(working_dir=str(docker_dir))


@pytest_asyncio.fixture
async def ssh_conn(ssh_dir: Path) -> SSHConnection:
    config = SSHConnectionConfig(host="mock-deploy-server")
    backend = MockSSHBackend(root_dir=str(ssh_dir))
    conn = SSHConnection(config=config, backend=backend)
    await conn.connect()
    yield conn
    if conn.is_connected:
        await conn.disconnect()


# ---------------------------------------------------------------------------
# Test: Multi-environment workflow without decorators
# ---------------------------------------------------------------------------


class TestMultiEnvWorkflow:
    """Simulate a cross-environment workflow: read locally, build in Docker, deploy via SSH."""

    @pytest.mark.asyncio
    async def test_cross_env_workflow(
        self,
        local_dir: Path,
        docker_dir: Path,
        docker_executor: MockContainerExecutor,
        ssh_conn: SSHConnection,
    ) -> None:
        # Create tool instances for each environment
        local_read = EnvLocalReadFile(working_dir=str(local_dir))
        docker_write = EnvDockerWriteFile(
            container_id="mock-ctr",
            executor=docker_executor,
            working_dir=str(docker_dir),
        )
        docker_exec = EnvDockerExec(
            container_id="mock-ctr",
            executor=docker_executor,
            working_dir=str(docker_dir),
        )
        ssh_write = EnvSSHWriteFile(ssh_connection=ssh_conn)
        ssh_exists = EnvSSHFileExists(ssh_connection=ssh_conn)

        # Step 1: Read config from local environment
        result = await local_read.execute({"path": "config.yaml"})
        assert result.success is True
        assert "my-app" in result.output
        config_content = result.output

        # Step 2: Write build script to Docker environment
        build_script = f"#!/bin/bash\necho 'Building {config_content.strip()}'\necho 'BUILD_OK' > /tmp/status\n"
        result = await docker_write.execute(
            {"path": "build.sh", "content": build_script}
        )
        assert result.success is True

        # Step 3: Execute build in Docker environment
        result = await docker_exec.execute({"command": "bash build.sh"})
        assert result.success is True
        assert result.output["exit_code"] == 0
        assert "Building" in result.output["stdout"]

        # Step 4: Upload artifact to SSH environment
        artifact_content = "ARTIFACT_DATA_v2.0"
        result = await ssh_write.execute(
            {"path": "/deploy/artifact.tar", "content": artifact_content}
        )
        assert result.success is True

        # Step 5: Verify artifact exists on SSH environment
        result = await ssh_exists.execute({"path": "/deploy/artifact.tar"})
        assert result.success is True
        assert result.output is True


# ---------------------------------------------------------------------------
# Test: Multi-environment workflow WITH Logging decorator
# ---------------------------------------------------------------------------


class TestMultiEnvWithLogging:
    """All three environments wrapped with Logging decorator — verify all ops logged."""

    @pytest.mark.asyncio
    async def test_all_operations_logged_across_environments(
        self,
        local_dir: Path,
        docker_dir: Path,
        docker_executor: MockContainerExecutor,
        ssh_conn: SSHConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Create tool instances
        local_read = EnvLocalReadFile(working_dir=str(local_dir))
        docker_write = EnvDockerWriteFile(
            container_id="mock-ctr",
            executor=docker_executor,
            working_dir=str(docker_dir),
        )
        docker_exec = EnvDockerExec(
            container_id="mock-ctr",
            executor=docker_executor,
            working_dir=str(docker_dir),
        )
        ssh_write = EnvSSHWriteFile(ssh_connection=ssh_conn)
        ssh_exists = EnvSSHFileExists(ssh_connection=ssh_conn)

        # Single Logging decorator shared across all environments
        logging_decorator = LoggingDecorator()
        stack = [logging_decorator]

        with caplog.at_level(logging.INFO):
            # Step 1: Read from local
            r = await simulate_tool_call_with_decorators(
                stack, local_read, {"path": "config.yaml"}
            )
            assert r["success"] is True

            # Step 2: Write to Docker
            r = await simulate_tool_call_with_decorators(
                stack, docker_write, {"path": "build.sh", "content": "echo hello"}
            )
            assert r["success"] is True

            # Step 3: Exec in Docker
            r = await simulate_tool_call_with_decorators(
                stack, docker_exec, {"command": "echo done"}
            )
            assert r["success"] is True

            # Step 4: Write to SSH
            r = await simulate_tool_call_with_decorators(
                stack, ssh_write, {"path": "/deploy/app.tar", "content": "data"}
            )
            assert r["success"] is True

            # Step 5: Check existence on SSH
            r = await simulate_tool_call_with_decorators(
                stack, ssh_exists, {"path": "/deploy/app.tar"}
            )
            assert r["success"] is True
            assert r["output"] is True

        # Verify ALL 5 operations were logged
        log_messages = " ".join(r.message for r in caplog.records)

        # Each env.* tool should appear in the log
        assert "env.read_file" in log_messages, "Local read_file not logged"
        assert "env.write_file" in log_messages, "write_file not logged"
        assert "env.exec" in log_messages, "Docker exec not logged"
        assert "env.file_exists" in log_messages, "SSH file_exists not logged"

        # All operations should show success
        assert log_messages.count("success=True") == 5, (
            f"Expected 5 successful log entries, got {log_messages.count('success=True')}"
        )

    @pytest.mark.asyncio
    async def test_tools_have_distinct_names(
        self,
        local_dir: Path,
        docker_dir: Path,
        docker_executor: MockContainerExecutor,
        ssh_conn: SSHConnection,
    ) -> None:
        """All tools use the env.* namespace — verify they share the common shape."""
        local_read = EnvLocalReadFile(working_dir=str(local_dir))
        docker_write = EnvDockerWriteFile(
            container_id="mock-ctr",
            executor=docker_executor,
            working_dir=str(docker_dir),
        )
        ssh_exists = EnvSSHFileExists(ssh_connection=ssh_conn)

        # All tools share the env.* namespace
        assert local_read.name == "env.read_file"
        assert docker_write.name == "env.write_file"
        assert ssh_exists.name == "env.file_exists"

        # All tools have descriptions
        assert local_read.description
        assert docker_write.description
        assert ssh_exists.description

        # All tools provide JSON schemas
        assert "properties" in local_read.get_schema()
        assert "properties" in docker_write.get_schema()
        assert "properties" in ssh_exists.get_schema()
