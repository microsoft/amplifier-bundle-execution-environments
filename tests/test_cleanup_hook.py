"""Tests for the session:end cleanup hook.

Verifies that EnvCleanupHandler tears down all environment instances
when a session ends, and that mount() wires everything correctly.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifier_core import HookResult

from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# Stub backend (matches pattern from test_management.py)
# ---------------------------------------------------------------------------


class StubBackend:
    """Minimal backend that tracks cleanup calls."""

    def __init__(self, env_type: str = "local") -> None:
        self._env_type = env_type
        self.cleaned_up = False

    @property
    def env_type(self) -> str:
        return self._env_type

    def working_directory(self) -> str:
        return "/stub"

    def platform(self) -> str:
        return "linux"

    def os_version(self) -> str:
        return "stub"

    async def exec_command(
        self,
        cmd: str,
        timeout: float | None = None,
        workdir: str | None = None,
        env_vars: dict[str, str] | None = None,
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

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        return []

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        return ""

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        return []

    async def cleanup(self) -> None:
        self.cleaned_up = True

    def info(self) -> dict[str, Any]:
        return {"type": self._env_type}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> EnvironmentRegistry:
    return EnvironmentRegistry()


@pytest.fixture
def registry_with_instances(registry: EnvironmentRegistry) -> EnvironmentRegistry:
    """Registry pre-loaded with two stub instances."""
    registry.register("local", StubBackend("local"), "local")
    registry.register("build", StubBackend("docker"), "docker")
    return registry


# ---------------------------------------------------------------------------
# TestEnvCleanupHandler
# ---------------------------------------------------------------------------


class TestCleanupHandlerCallsDestroyAll:
    """session:end event triggers registry.destroy_all()."""

    def test_cleanup_handler_calls_destroy_all(
        self,
        registry_with_instances: EnvironmentRegistry,
    ) -> None:
        from amplifier_module_hooks_env_all import EnvCleanupHandler

        handler = EnvCleanupHandler(registry_with_instances)
        asyncio.run(
            handler.handle_session_end("session:end", {"session_id": "test-123"})
        )

        # Both backends should have been cleaned up
        assert registry_with_instances.list_instances() == []


class TestCleanupHandlerReturnsResult:
    """Handler always returns HookResult(action="continue")."""

    def test_cleanup_handler_returns_continue(
        self,
        registry_with_instances: EnvironmentRegistry,
    ) -> None:
        from amplifier_module_hooks_env_all import EnvCleanupHandler

        handler = EnvCleanupHandler(registry_with_instances)
        result = asyncio.run(
            handler.handle_session_end("session:end", {"session_id": "test-123"})
        )

        assert isinstance(result, HookResult)
        assert result.action == "continue"


class TestCleanupHandlerToleratesEmptyRegistry:
    """Works with no instances registered."""

    def test_cleanup_tolerates_empty_registry(
        self,
        registry: EnvironmentRegistry,
    ) -> None:
        from amplifier_module_hooks_env_all import EnvCleanupHandler

        handler = EnvCleanupHandler(registry)
        result = asyncio.run(
            handler.handle_session_end("session:end", {"session_id": "test-456"})
        )

        assert isinstance(result, HookResult)
        assert result.action == "continue"


class TestCleanupHandlerToleratesFailures:
    """Cleanup continues past individual backend failures."""

    def test_cleanup_tolerates_backend_failure(
        self,
        registry: EnvironmentRegistry,
    ) -> None:
        from amplifier_module_hooks_env_all import EnvCleanupHandler

        # Create a backend that fails on cleanup
        failing_backend = StubBackend("docker")
        failing_backend.cleanup = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        registry.register("failing", failing_backend, "docker")

        handler = EnvCleanupHandler(registry)
        # Should NOT raise — cleanup failures are logged, not propagated
        result = asyncio.run(
            handler.handle_session_end("session:end", {"session_id": "test-789"})
        )

        assert isinstance(result, HookResult)
        assert result.action == "continue"


# ---------------------------------------------------------------------------
# TestMount
# ---------------------------------------------------------------------------


class TestMountRegistersHook:
    """mount() wires up the registry, local instance, capability, and hook."""

    def test_mount_registers_session_end_hook(self) -> None:
        from amplifier_module_hooks_env_all import mount

        # Build a mock coordinator with hooks.register
        coordinator = MagicMock()
        coordinator.hooks = MagicMock()
        coordinator.hooks.register = MagicMock()

        asyncio.run(mount(coordinator, {}))

        # Hook was registered for session:end
        coordinator.hooks.register.assert_called_once()
        call_args = coordinator.hooks.register.call_args
        assert call_args[0][0] == "session:end"  # first positional arg is event name
        assert callable(call_args[0][1])  # second positional arg is the handler

    def test_mount_stores_registry_as_capability(self) -> None:
        from amplifier_module_hooks_env_all import mount

        coordinator = MagicMock()
        coordinator.hooks = MagicMock()
        coordinator.get_capability = MagicMock(return_value=None)

        asyncio.run(mount(coordinator, {}))

        # Registry stored as capability
        coordinator.register_capability.assert_called_once()
        cap_name, cap_value = coordinator.register_capability.call_args[0]
        assert cap_name == "env_registry"
        assert isinstance(cap_value, EnvironmentRegistry)

    def test_mount_creates_local_instance(self) -> None:
        from amplifier_module_hooks_env_all import mount

        coordinator = MagicMock()
        coordinator.hooks = MagicMock()
        coordinator.get_capability = MagicMock(return_value=None)

        asyncio.run(mount(coordinator, {}))

        # The registry should have a "local" instance
        cap_value = coordinator.register_capability.call_args[0][1]
        instances = cap_value.list_instances()
        assert len(instances) == 1
        assert instances[0]["name"] == "local"
        assert instances[0]["type"] == "local"

    def test_mount_returns_module_metadata(self) -> None:
        from amplifier_module_hooks_env_all import mount

        coordinator = MagicMock()
        coordinator.hooks = MagicMock()

        result = asyncio.run(mount(coordinator, {}))

        assert result["name"] == "hooks-env-all"
        assert "version" in result


# ---------------------------------------------------------------------------
# B.5: Cleanup hook skips unowned instances
# ---------------------------------------------------------------------------


class TestCleanupSkipsUnowned:
    """Cleanup only destroys owned instances, leaves unowned intact."""

    def test_cleanup_skips_unowned_instances(
        self,
        registry: EnvironmentRegistry,
    ) -> None:
        """Register owned + unowned; cleanup only destroys owned."""
        from amplifier_module_hooks_env_all import EnvCleanupHandler

        owned_backend = StubBackend("docker")
        unowned_backend = StubBackend("docker")

        registry.register("owned-inst", owned_backend, "docker", owned=True)
        registry.register("unowned-inst", unowned_backend, "docker", owned=False)

        handler = EnvCleanupHandler(registry)
        asyncio.run(
            handler.handle_session_end("session:end", {"session_id": "test-owned"})
        )

        # Owned backend was cleaned up
        assert owned_backend.cleaned_up is True
        # Unowned backend was NOT cleaned up
        assert unowned_backend.cleaned_up is False
        # Unowned instance still in registry
        remaining = registry.list_instances()
        assert len(remaining) == 1
        assert remaining[0]["name"] == "unowned-inst"

    def test_cleanup_logs_skipped_instances(
        self,
        registry: EnvironmentRegistry,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify logging mentions skipped unowned instances."""
        import logging

        from amplifier_module_hooks_env_all import EnvCleanupHandler

        unowned_backend = StubBackend("docker")
        registry.register("ext-db", unowned_backend, "docker", owned=False)

        handler = EnvCleanupHandler(registry)
        with caplog.at_level(logging.INFO):
            asyncio.run(
                handler.handle_session_end("session:end", {"session_id": "test-log"})
            )

        assert "skipping" in caplog.text.lower()
        assert "ext-db" in caplog.text
