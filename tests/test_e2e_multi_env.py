"""End-to-end multi-environment integration test.

Validates that local, Docker, and SSH environment backends can coexist and
work together in a single workflow — with LoggingWrapper wrapping all
three environments simultaneously.

All backends are mocked (no real Docker daemon or SSH server needed):
- Local: LocalBackend uses tmp_path directly
- Docker: DockerBackend uses a mock containers_invoke running commands locally
- SSH: SSHBackendWrapper uses a mock exec_fn running commands locally

Run with:
    PYTHONPATH=lib python3 -m pytest tests/test_e2e_multi_env.py -v
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from amplifier_env_common.backends.local import LocalBackend
from amplifier_env_common.backends.docker import DockerBackend
from amplifier_env_common.backends.ssh import SSHBackendWrapper
from amplifier_env_common.protocol import EnvironmentBackend
from amplifier_env_common.wrappers.logging_wrapper import LoggingWrapper


# ---------------------------------------------------------------------------
# Mock helpers for Docker and SSH backends
# ---------------------------------------------------------------------------


@dataclass
class MockInvokeResult:
    """Result returned by mock containers_invoke — mimics the containers tool."""

    success: bool = True
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


def make_mock_containers_invoke(working_dir: str):
    """Create a mock containers_invoke that runs shell commands locally."""

    async def mock_invoke(input_dict: dict[str, Any]) -> MockInvokeResult:
        operation = input_dict.get("operation", "")
        if operation == "destroy":
            return MockInvokeResult(success=True, output={})

        command = input_dict.get("command", "")
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        return MockInvokeResult(
            success=True,
            output={
                "stdout": stdout_bytes.decode() if stdout_bytes else "",
                "stderr": stderr_bytes.decode() if stderr_bytes else "",
                "exit_code": proc.returncode or 0,
            },
        )

    return mock_invoke


@dataclass
class MockSSHExecResult:
    """Result returned by mock SSH exec_fn."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


def make_mock_ssh_exec(root_dir: str):
    """Create a mock SSH exec_fn that runs shell commands locally in root_dir."""

    async def mock_exec(cmd: str, timeout: float | None = None) -> MockSSHExecResult:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=root_dir,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        return MockSSHExecResult(
            stdout=stdout_bytes.decode() if stdout_bytes else "",
            stderr=stderr_bytes.decode() if stderr_bytes else "",
            exit_code=proc.returncode or 0,
        )

    return mock_exec


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
def local_backend(local_dir: Path) -> LocalBackend:
    return LocalBackend(working_dir=str(local_dir))


@pytest.fixture
def docker_backend(docker_dir: Path) -> DockerBackend:
    return DockerBackend(
        containers_invoke=make_mock_containers_invoke(str(docker_dir)),
        container_id="mock-ctr",
        working_dir=str(docker_dir),
    )


@pytest.fixture
def ssh_backend(ssh_dir: Path) -> SSHBackendWrapper:
    return SSHBackendWrapper(
        exec_fn=make_mock_ssh_exec(str(ssh_dir)),
        host="mock-deploy-server",
    )


# ---------------------------------------------------------------------------
# Test: Multi-environment workflow without wrappers
# ---------------------------------------------------------------------------


class TestMultiEnvWorkflow:
    """Simulate a cross-environment workflow: read locally, build in Docker, deploy via SSH."""

    @pytest.mark.asyncio
    async def test_cross_env_workflow(
        self,
        local_backend: LocalBackend,
        docker_backend: DockerBackend,
        ssh_backend: SSHBackendWrapper,
    ) -> None:
        # Step 1: Read config from local environment
        config_content = await local_backend.read_file("config.yaml")
        assert "my-app" in config_content

        # Step 2: Write build script to Docker environment
        build_script = (
            f"#!/bin/bash\necho 'Building {config_content.strip()}'\n"
            "echo 'BUILD_OK' > /tmp/status\n"
        )
        await docker_backend.write_file("build.sh", build_script)

        # Step 3: Execute build in Docker environment
        exec_result = await docker_backend.exec_command("bash build.sh")
        assert exec_result.exit_code == 0
        assert "Building" in exec_result.stdout

        # Step 4: Upload artifact to SSH environment (relative path for mock)
        artifact_content = "ARTIFACT_DATA_v2.0"
        await ssh_backend.write_file("deploy/artifact.tar", artifact_content)

        # Step 5: Verify artifact exists on SSH environment
        exists = await ssh_backend.file_exists("deploy/artifact.tar")
        assert exists is True


# ---------------------------------------------------------------------------
# Test: Multi-environment workflow WITH LoggingWrapper
# ---------------------------------------------------------------------------


class TestMultiEnvWithLogging:
    """All three environments wrapped with LoggingWrapper — verify all ops logged."""

    @pytest.mark.asyncio
    async def test_all_operations_logged_across_environments(
        self,
        local_backend: LocalBackend,
        docker_backend: DockerBackend,
        ssh_backend: SSHBackendWrapper,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Wrap all backends with LoggingWrapper
        logged_local = LoggingWrapper(local_backend, logger_name="env")
        logged_docker = LoggingWrapper(docker_backend, logger_name="env")
        logged_ssh = LoggingWrapper(ssh_backend, logger_name="env")

        with caplog.at_level(logging.DEBUG, logger="env"):
            # Step 1: Read from local (logged at DEBUG)
            content = await logged_local.read_file("config.yaml")
            assert "my-app" in content

            # Step 2: Write to Docker (logged at INFO)
            await logged_docker.write_file("build.sh", "echo hello")

            # Step 3: Exec in Docker (logged at INFO)
            exec_result = await logged_docker.exec_command("echo done")
            assert exec_result.exit_code == 0

            # Step 4: Write to SSH (logged at INFO)
            await logged_ssh.write_file("deploy/app.tar", "data")

            # Step 5: Exec on SSH to verify (logged at INFO)
            exec_result = await logged_ssh.exec_command("echo deployed")
            assert exec_result.exit_code == 0

        # Verify operations were logged across all three environments
        log_messages = " ".join(r.message for r in caplog.records)

        # Each env type should appear in the logs
        assert "env [local]" in log_messages, "Local operations not logged"
        assert "env [docker]" in log_messages, "Docker operations not logged"
        assert "env [ssh]" in log_messages, "SSH operations not logged"

        # Verify specific operations were logged
        assert "read" in log_messages, "read_file not logged"
        assert "write" in log_messages, "write_file not logged"
        assert "exec" in log_messages, "exec_command not logged"

    @pytest.mark.asyncio
    async def test_backends_have_distinct_env_types(
        self,
        local_backend: LocalBackend,
        docker_backend: DockerBackend,
        ssh_backend: SSHBackendWrapper,
    ) -> None:
        """All backends report distinct env_type values and implement the protocol."""
        # All backends report distinct types
        assert local_backend.env_type == "local"
        assert docker_backend.env_type == "docker"
        assert ssh_backend.env_type == "ssh"

        # All backends satisfy the EnvironmentBackend protocol
        assert isinstance(local_backend, EnvironmentBackend)
        assert isinstance(docker_backend, EnvironmentBackend)
        assert isinstance(ssh_backend, EnvironmentBackend)

        # All backends provide info dicts
        assert isinstance(local_backend.info(), dict)
        assert isinstance(docker_backend.info(), dict)
        assert isinstance(ssh_backend.info(), dict)
