"""Phase 4 Docker integration tests — instance model lifecycle.

These tests exercise the full env_create → env_exec → env_destroy lifecycle
using a REAL Docker daemon. They test the DockerBackend + EnvironmentRegistry
integration at the backend level, using the same _docker_cli_invoke pattern
as the Phase 3 integration tests.

Requirements:
    - Running Docker daemon accessible via ``docker`` CLI
    - Run with: ``pytest env-all/tests/integration/ -v --docker-integration``

Each test uses a unique container name and cleans up in a ``finally`` block
to prevent container leaks even on failure.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid

import pytest

from amplifier_core import ToolResult

from amplifier_env_common.backends.docker import DockerBackend
from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_name() -> str:
    """Return a unique container name to prevent collisions."""
    return f"env-test-phase4-{uuid.uuid4().hex[:12]}"


def _docker_available() -> bool:
    """Check whether the Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# Skip the entire module if Docker is not reachable (even with the flag).
if not _docker_available():
    pytest.skip("Docker daemon not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Docker CLI invoke shim (same pattern as Phase 3)
# ---------------------------------------------------------------------------


async def _docker_cli_invoke(input_dict: dict) -> ToolResult:
    """Invoke shim that translates containers tool calls to Docker CLI commands.

    Simulates what the real Amplifier containers tool does, but via direct
    subprocess calls so we can test the backend's translation layer against
    a real Docker daemon without the full Amplifier runtime.
    """
    operation = input_dict.get("operation")

    if operation == "create":
        name = input_dict.get("name", f"env-phase4-{uuid.uuid4().hex[:8]}")
        image = "alpine:3.20"
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            image,
            "sleep",
            "300",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error={"message": f"create failed: {stderr.decode().strip()}"},
            )
        return ToolResult(success=True, output={"container_id": name})

    elif operation == "exec":
        container = input_dict["container"]
        command = input_dict["command"]
        timeout = input_dict.get("timeout", 30)
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(success=False, error={"message": "exec timed out"})
        return ToolResult(
            success=True,
            output={
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "exit_code": proc.returncode,
            },
        )

    elif operation == "destroy":
        container = input_dict["container"]
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0:
            return ToolResult(success=False, error={"message": "destroy failed"})
        return ToolResult(success=True, output="destroyed")

    elif operation == "status":
        container = input_dict["container"]
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "--format",
            "{{.State.Status}}",
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error={"message": f"not found: {stderr.decode().strip()}"},
            )
        return ToolResult(success=True, output={"status": stdout.decode().strip()})

    return ToolResult(
        success=False,
        error={"message": f"Unknown operation: {operation}"},
    )


# ---------------------------------------------------------------------------
# Helper: check if a container exists via Docker CLI
# ---------------------------------------------------------------------------


async def _container_exists(name: str) -> bool:
    """Check if a container exists via Docker inspect."""
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "inspect",
        name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.docker_integration
class TestPhase4DockerLifecycle:
    """Full lifecycle tests for Phase 4 instance model with real Docker."""

    @pytest.mark.asyncio
    async def test_create_exec_destroy_lifecycle(self):
        """Full lifecycle: create → exec → read/write → destroy → verify gone."""
        name = _unique_name()
        registry = EnvironmentRegistry()

        try:
            # --- Create container via CLI shim ---
            create_result = await _docker_cli_invoke(
                {"operation": "create", "name": name}
            )
            assert create_result.success, (
                f"Container creation failed: {create_result.error}"
            )

            # --- Wire up DockerBackend + Registry ---
            backend = DockerBackend(
                containers_invoke=_docker_cli_invoke,
                container_id=name,
            )
            registry.register(name, backend, "docker")

            # Verify registration
            instances = registry.list_instances()
            assert len(instances) == 1
            assert instances[0]["name"] == name
            assert instances[0]["type"] == "docker"

            # --- Test exec_command ---
            result = await backend.exec_command("echo hello from phase4")
            assert "hello from phase4" in result.stdout
            assert result.exit_code == 0

            # --- Test write_file + read_file ---
            await backend.write_file("/tmp/phase4_test.txt", "phase4 content")
            content = await backend.read_file("/tmp/phase4_test.txt")
            assert "phase4 content" in content

            # --- Test file_exists ---
            exists = await backend.file_exists("/tmp/phase4_test.txt")
            assert exists is True

            missing = await backend.file_exists("/tmp/nonexistent_phase4.txt")
            assert missing is False

            # --- Test edit_file ---
            msg = await backend.edit_file(
                "/tmp/phase4_test.txt", "phase4 content", "edited content"
            )
            assert "Edited" in msg
            edited = await backend.read_file("/tmp/phase4_test.txt")
            assert "edited content" in edited

            # --- Test list_dir ---
            entries = await backend.list_dir("/tmp")
            names = [e.name for e in entries]
            assert "phase4_test.txt" in names

            # --- Test grep ---
            grep_result = await backend.grep("edited", path="/tmp/phase4_test.txt")
            assert "edited content" in grep_result

            # --- Test glob_files ---
            await backend.write_file("/tmp/phase4_glob_a.py", "# file a")
            await backend.write_file("/tmp/phase4_glob_b.py", "# file b")
            glob_result = await backend.glob_files("phase4_glob_*.py", path="/tmp")
            assert len(glob_result) == 2

            # --- Destroy via registry ---
            await registry.destroy(name)

            # Verify removed from registry
            assert registry.get(name) is None
            assert len(registry.list_instances()) == 0

            # --- Verify container is actually gone ---
            exists_after = await _container_exists(name)
            assert exists_after is False, "Container should be removed after destroy"

        finally:
            # Safety net: force-remove container even if assertions fail
            try:
                await _docker_cli_invoke({"operation": "destroy", "container": name})
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_exec_nonzero_exit_code(self):
        """DockerBackend correctly reports non-zero exit codes."""
        name = _unique_name()
        registry = EnvironmentRegistry()

        try:
            create_result = await _docker_cli_invoke(
                {"operation": "create", "name": name}
            )
            assert create_result.success

            backend = DockerBackend(
                containers_invoke=_docker_cli_invoke,
                container_id=name,
            )
            registry.register(name, backend, "docker")

            result = await backend.exec_command("ls /nonexistent_path_xyz")
            assert result.exit_code != 0
            assert result.stderr != ""

        finally:
            try:
                await _docker_cli_invoke({"operation": "destroy", "container": name})
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_registry_destroy_all(self):
        """Registry.destroy_all tears down all Docker instances."""
        name1 = _unique_name()
        name2 = _unique_name()
        registry = EnvironmentRegistry()

        try:
            # Create two containers
            r1 = await _docker_cli_invoke({"operation": "create", "name": name1})
            r2 = await _docker_cli_invoke({"operation": "create", "name": name2})
            assert r1.success and r2.success

            b1 = DockerBackend(containers_invoke=_docker_cli_invoke, container_id=name1)
            b2 = DockerBackend(containers_invoke=_docker_cli_invoke, container_id=name2)
            registry.register(name1, b1, "docker")
            registry.register(name2, b2, "docker")

            assert len(registry.list_instances()) == 2

            # Destroy all
            await registry.destroy_all()

            assert len(registry.list_instances()) == 0

            # Both containers should be gone
            assert await _container_exists(name1) is False
            assert await _container_exists(name2) is False

        finally:
            for n in (name1, name2):
                try:
                    await _docker_cli_invoke({"operation": "destroy", "container": n})
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Compose helpers
# ---------------------------------------------------------------------------


def _compose_available() -> bool:
    """Check whether docker compose (v2 plugin) is available."""
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _unique_project() -> str:
    """Return a unique compose project name (must be lowercase, no dots)."""
    return f"envtest{uuid.uuid4().hex[:10]}"


_COMPOSE_TEMPLATE = """\
services:
  app:
    image: alpine:3.20
    command: sleep 3600
"""


async def _compose_up(compose_file: str, project: str) -> None:
    """Bring up a compose stack."""
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "-f",
        compose_file,
        "-p",
        project,
        "up",
        "-d",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = f"compose up failed: {stderr.decode().strip()}"
        raise RuntimeError(msg)


async def _compose_down(compose_file: str, project: str) -> None:
    """Tear down a compose stack (best-effort)."""
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "-f",
        compose_file,
        "-p",
        project,
        "down",
        "--remove-orphans",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()


async def _wait_container_running(name: str, timeout_sec: int = 30) -> None:
    """Poll until a container is running (or raise)."""
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "--format",
            "{{.State.Running}}",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if stdout.decode().strip() == "true":
            return
        await asyncio.sleep(1)
    msg = f"Container {name} did not start within {timeout_sec}s"
    raise TimeoutError(msg)


def _make_compose_invoke(compose_file: str):
    """Create a containers-invoke shim that handles compose-aware destroy.

    For exec/status operations, delegates to the standard _docker_cli_invoke.
    For destroy with compose_project, runs ``docker compose down``.
    """

    async def invoke(input_dict: dict) -> ToolResult:
        operation = input_dict.get("operation")

        if operation == "destroy" and input_dict.get("compose_project"):
            project = input_dict["compose_project"]
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "compose",
                "-f",
                compose_file,
                "-p",
                project,
                "down",
                "--remove-orphans",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    error={
                        "message": f"compose down failed: {stderr.decode().strip()}"
                    },
                )
            return ToolResult(success=True, output="compose stack destroyed")

        return await _docker_cli_invoke(input_dict)

    return invoke


# ---------------------------------------------------------------------------
# Compose lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.docker_integration
class TestPhase4ComposeLifecycle:
    """Integration tests for compose support in DockerBackend."""

    @pytest.mark.asyncio
    async def test_compose_lifecycle(self, tmp_path):
        """Full lifecycle: compose up → exec in service → compose down."""
        if not _compose_available():
            pytest.skip("docker compose (v2) not available")

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(_COMPOSE_TEMPLATE)

        project = _unique_project()
        container_name = f"{project}-app-1"

        try:
            # Bring up the compose stack
            await _compose_up(str(compose_file), project)

            # Wait for the app container to be running
            await _wait_container_running(container_name)

            # Create a DockerBackend attached to the compose service
            backend = DockerBackend(
                containers_invoke=_docker_cli_invoke,
                container_id=container_name,
                compose_project=project,
            )

            # exec works inside the compose container
            result = await backend.exec_command("echo hello from compose")
            assert result.exit_code == 0
            assert "hello from compose" in result.stdout

            # info() includes compose_project
            info = backend.info()
            assert info["compose_project"] == project
            assert info["container_id"] == container_name

        finally:
            await _compose_down(str(compose_file), project)

    @pytest.mark.asyncio
    async def test_compose_cleanup_destroys_stack(self, tmp_path):
        """Verify DockerBackend.cleanup() with compose_project tears down the stack."""
        if not _compose_available():
            pytest.skip("docker compose (v2) not available")

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(_COMPOSE_TEMPLATE)

        project = _unique_project()
        container_name = f"{project}-app-1"

        try:
            # Bring up the compose stack
            await _compose_up(str(compose_file), project)
            await _wait_container_running(container_name)

            # Verify container exists before cleanup
            assert await _container_exists(container_name) is True

            # Create a DockerBackend with compose-aware invoke
            invoke = _make_compose_invoke(str(compose_file))
            backend = DockerBackend(
                containers_invoke=invoke,
                container_id=container_name,
                compose_project=project,
            )

            # cleanup() should route through compose down
            await backend.cleanup()

            # Container should be gone
            assert await _container_exists(container_name) is False

        finally:
            # Safety net in case cleanup didn't work
            await _compose_down(str(compose_file), project)


# ---------------------------------------------------------------------------
# Attach lifecycle tests (Phase 4.2 cross-session sharing)
# ---------------------------------------------------------------------------


@pytest.mark.docker_integration
class TestPhase4AttachLifecycle:
    """Integration tests for parent-creates / child-attaches cross-session sharing."""

    @pytest.mark.asyncio
    async def test_parent_child_attach_pattern(self):
        """Parent (owned) and child (unowned) share a container.

        Flow:
        1. Create container externally
        2. Parent registry: register with owned=True
        3. Child registry: register same container with owned=False
        4. Child exec works
        5. Child destroy_all() does NOT destroy container (unowned)
        6. Container still exists
        7. Parent exec still works
        8. Parent destroy_all() DOES destroy container (owned)
        9. Container is gone
        """
        name = _unique_name()
        parent_registry = EnvironmentRegistry()
        child_registry = EnvironmentRegistry()

        try:
            # --- Step 1: Create container externally ---
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "alpine:3.20",
                "sleep",
                "3600",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            assert proc.returncode == 0, (
                f"Container creation failed: {stderr.decode().strip()}"
            )

            # --- Step 2: Parent registers with owned=True ---
            parent_backend = DockerBackend(
                containers_invoke=_docker_cli_invoke,
                container_id=name,
            )
            parent_registry.register(name, parent_backend, "docker", owned=True)

            # --- Step 3: Child registers same container with owned=False ---
            child_backend = DockerBackend(
                containers_invoke=_docker_cli_invoke,
                container_id=name,
            )
            child_registry.register(name, child_backend, "docker", owned=False)

            # Verify both registrations reflect owned flag
            parent_instances = parent_registry.list_instances()
            assert len(parent_instances) == 1
            assert parent_instances[0]["owned"] is True

            child_instances = child_registry.list_instances()
            assert len(child_instances) == 1
            assert child_instances[0]["owned"] is False

            # --- Step 4: Child exec works ---
            child_result = await child_backend.exec_command("echo hello from child")
            assert child_result.exit_code == 0
            assert "hello from child" in child_result.stdout

            # --- Step 5: Child destroy_all() does NOT destroy container ---
            await child_registry.destroy_all()

            # Child registry should still have the unowned instance
            assert len(child_registry.list_instances()) == 1

            # --- Step 6: Container still exists ---
            assert await _container_exists(name) is True, (
                "Container should survive child destroy_all (unowned)"
            )

            # --- Step 7: Parent exec still works ---
            parent_result = await parent_backend.exec_command("echo still alive")
            assert parent_result.exit_code == 0
            assert "still alive" in parent_result.stdout

            # --- Step 8: Parent destroy_all() DOES destroy container ---
            await parent_registry.destroy_all()

            # Parent registry should be empty
            assert len(parent_registry.list_instances()) == 0

            # --- Step 9: Container is gone ---
            assert await _container_exists(name) is False, (
                "Container should be destroyed by parent destroy_all (owned)"
            )

        finally:
            # Safety net: force-remove container even if assertions fail
            try:
                await _docker_cli_invoke({"operation": "destroy", "container": name})
            except Exception:
                pass
