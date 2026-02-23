"""Phase 4 SSH integration tests — instance model lifecycle.

These tests exercise the SSHBackendWrapper against a REAL sshd container
running in Docker. They verify that the Phase 4 instance model works
end-to-end with the SSH backend: exec commands, read/write files, and
clean up via the EnvironmentRegistry.

Phase 4.2 adds SSH credential auto-discovery tests that verify
discover_ssh_config() works end-to-end against the real system and
a real sshd container.

Requirements:
    - Running Docker daemon accessible via ``docker`` CLI
    - Run with: ``pytest env-all/tests/integration/ -v --ssh-integration``
"""

from __future__ import annotations

import os
import uuid

import asyncssh
import pytest
import pytest_asyncio

from amplifier_module_tools_env_ssh.async_backend import AsyncSSHBackend
from amplifier_module_tools_env_ssh.connection import SSHConnection, SSHConnectionConfig

from amplifier_env_common.backends.ssh import SSHBackendWrapper
from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_path(prefix: str = "/tmp/phase4-ssh") -> str:
    """Return a unique remote path to prevent test collisions."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ssh_connection(sshd_container):
    """Create AsyncSSHBackend + SSHConnection, connect, yield, disconnect."""
    config = SSHConnectionConfig(
        host=sshd_container["host"],
        port=sshd_container["port"],
        username=sshd_container["username"],
        key_file=sshd_container["key_file"],
        known_hosts=sshd_container["known_hosts"],
        connect_timeout=15,
    )
    backend = AsyncSSHBackend(config)
    conn = SSHConnection(config=config, backend=backend)
    await conn.connect()
    try:
        yield conn
    finally:
        await conn.disconnect()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.ssh_integration
class TestPhase4SSHLifecycle:
    """Full lifecycle tests for Phase 4 instance model with real SSH."""

    @pytest.mark.asyncio
    async def test_ssh_backend_lifecycle(self, sshd_container, ssh_connection):
        """SSHBackendWrapper: exec, write, read, file_exists, cleanup."""
        backend = SSHBackendWrapper(
            exec_fn=ssh_connection.exec_command,
            host=sshd_container["host"],
            disconnect_fn=ssh_connection.disconnect,
        )

        # Test exec
        result = await backend.exec_command("echo hello from phase4 ssh")
        assert "hello from phase4 ssh" in result.stdout
        assert result.exit_code == 0

        # Test write + read
        test_path = _unique_path() + "/test.txt"
        await backend.write_file(test_path, "ssh phase4 content")
        content = await backend.read_file(test_path)
        assert "ssh phase4 content" in content

        # Test file_exists (positive)
        exists = await backend.file_exists(test_path)
        assert exists is True

        # Test file_exists (negative)
        missing = await backend.file_exists("/tmp/nonexistent-" + uuid.uuid4().hex)
        assert missing is False

        # Test edit_file
        msg = await backend.edit_file(test_path, "ssh phase4 content", "edited content")
        assert "Edited" in msg
        edited = await backend.read_file(test_path)
        assert "edited content" in edited

        # Test list_dir
        parent_dir = test_path.rsplit("/", 1)[0]
        entries = await backend.list_dir(parent_dir)
        names = [e.name for e in entries]
        assert "test.txt" in names

        # Test grep
        grep_result = await backend.grep("edited", path=test_path)
        assert "edited content" in grep_result

        # Test glob_files
        glob_path = _unique_path()
        await backend.write_file(f"{glob_path}/a.py", "# file a")
        await backend.write_file(f"{glob_path}/b.py", "# file b")
        glob_result = await backend.glob_files("*.py", path=glob_path)
        assert len(glob_result) == 2

        # Cleanup (disconnects SSH — don't use ssh_connection after this)
        await backend.cleanup()

    @pytest.mark.asyncio
    async def test_ssh_registry_lifecycle(self, sshd_container):
        """SSHBackendWrapper registered in EnvironmentRegistry: use + destroy."""
        config = SSHConnectionConfig(
            host=sshd_container["host"],
            port=sshd_container["port"],
            username=sshd_container["username"],
            key_file=sshd_container["key_file"],
            known_hosts=sshd_container["known_hosts"],
            connect_timeout=15,
        )
        async_backend = AsyncSSHBackend(config)
        conn = SSHConnection(config=config, backend=async_backend)
        await conn.connect()

        try:
            instance_name = f"ssh-phase4-{uuid.uuid4().hex[:8]}"
            backend = SSHBackendWrapper(
                exec_fn=conn.exec_command,
                host=sshd_container["host"],
                disconnect_fn=conn.disconnect,
            )

            # Register in registry
            registry = EnvironmentRegistry()
            registry.register(instance_name, backend, "ssh")

            # Verify registration
            instances = registry.list_instances()
            assert len(instances) == 1
            assert instances[0]["name"] == instance_name
            assert instances[0]["type"] == "ssh"

            # Use via registry.get()
            retrieved = registry.get(instance_name)
            assert retrieved is not None
            assert retrieved is backend

            # Execute a command through retrieved backend
            result = await retrieved.exec_command("echo registry-test")
            assert "registry-test" in result.stdout
            assert result.exit_code == 0

            # Destroy via registry (calls backend.cleanup → disconnect)
            await registry.destroy(instance_name)

            # Verify removed from registry
            assert registry.get(instance_name) is None
            assert len(registry.list_instances()) == 0

        except Exception:
            # Safety net: disconnect on failure
            await conn.disconnect()
            raise


@pytest.mark.ssh_integration
class TestPhase4SSHDiscovery:
    """Integration tests for SSH credential auto-discovery (Phase 4.2)."""

    def test_discover_ssh_config_finds_current_user(self):
        """Verify discovery chain finds the current user when no ssh config match."""
        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        # Use a hostname that won't match any ssh config entry
        result = discover_ssh_config("nonexistent-host-12345")

        # Should still discover the current user
        assert "username" in result
        assert len(result["username"]) > 0

    def test_discover_finds_default_key(self):
        """Verify discovery chain finds a default SSH key if one exists."""
        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        result = discover_ssh_config("any-host")

        # If any default keys exist, should discover one
        default_keys = [
            os.path.expanduser("~/.ssh/id_ed25519"),
            os.path.expanduser("~/.ssh/id_rsa"),
            os.path.expanduser("~/.ssh/id_ecdsa"),
        ]
        has_key = any(os.path.exists(k) for k in default_keys)
        if has_key:
            assert "key_file" in result
            assert os.path.exists(result["key_file"])

    @pytest.mark.asyncio
    async def test_ssh_connect_with_discovery(self, sshd_container):
        """Verify SSH connection works with auto-discovered credentials against real sshd."""
        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        # The sshd_container fixture provides a real sshd with known credentials.
        # We can't test full auto-discovery against it (it uses ephemeral keys),
        # but we CAN test that the discovery chain runs without errors
        # and that explicitly provided credentials work alongside discovery.

        host = sshd_container["host"]
        port = sshd_container["port"]
        username = sshd_container["username"]
        key_file = sshd_container["key_file"]
        known_hosts = sshd_container["known_hosts"]

        # Run discovery (will find current user but not matching ssh config for localhost)
        discovered = discover_ssh_config(host)
        assert isinstance(discovered, dict)

        # Connect using explicit credentials (simulating explicit params overriding discovery)
        conn = await asyncssh.connect(
            host,
            port=port,
            username=username,
            client_keys=[key_file],
            known_hosts=known_hosts,
        )

        try:
            # Create SSHBackendWrapper with the connection
            async def exec_fn(cmd, timeout=None, workdir=None):
                from amplifier_env_common.models import EnvExecResult

                full_cmd = f"cd {workdir} && {cmd}" if workdir else cmd
                result = await conn.run(full_cmd)
                return EnvExecResult(
                    stdout=str(result.stdout) if result.stdout else "",
                    stderr=str(result.stderr) if result.stderr else "",
                    exit_code=result.exit_status or 0,
                )

            backend = SSHBackendWrapper(
                exec_fn=exec_fn,
                host=host,
                disconnect_fn=conn.close,
            )

            # Verify it works
            result = await backend.exec_command("echo discovery_test")
            assert "discovery_test" in result.stdout
        finally:
            conn.close()
