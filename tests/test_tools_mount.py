"""Tests for tools-env-all mount function.

Verifies that mount() retrieves the shared EnvironmentRegistry from
coordinator capabilities, creates all 11 tools, and registers them.
"""

from __future__ import annotations

import asyncio
from typing import Any


from amplifier_env_common.backends.local import LocalBackend
from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class MockCoordinator:
    """Minimal coordinator stub that tracks mount calls."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Any] = {}
        self._mounted_tools: dict[str, Any] = {}

    def get(self, kind: str, name: str) -> Any:
        return None

    def register_capability(self, name: str, value: Any) -> None:
        self._capabilities[name] = value

    def get_capability(self, name: str) -> Any:
        return self._capabilities.get(name)

    async def mount(self, kind: str, tool: Any, name: str = "") -> None:
        if kind == "tools":
            self._mounted_tools[name] = tool


EXPECTED_TOOL_NAMES = sorted(
    [
        "env_create",
        "env_destroy",
        "env_list",
        "env_exec",
        "env_read_file",
        "env_write_file",
        "env_edit_file",
        "env_grep",
        "env_glob",
        "env_list_dir",
        "env_file_exists",
    ]
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestToolsMount:
    """Tests for the tools-env-all mount() function."""

    def test_mount_registers_11_tools(self) -> None:
        """mount() registers exactly 11 tools with coordinator."""
        from amplifier_module_tools_env_all import mount

        coordinator = MockCoordinator()
        registry = EnvironmentRegistry()
        registry.register("local", LocalBackend(working_dir="/tmp"), "local")
        coordinator.register_capability("env_registry", registry)

        asyncio.run(mount(coordinator))

        assert len(coordinator._mounted_tools) == 11

    def test_mount_retrieves_registry_from_capability(self) -> None:
        """mount() uses the registry from coordinator.get_capability('env_registry')."""
        from amplifier_module_tools_env_all import mount

        coordinator = MockCoordinator()
        registry = EnvironmentRegistry()
        registry.register("local", LocalBackend(working_dir="/tmp"), "local")
        coordinator.register_capability("env_registry", registry)

        asyncio.run(mount(coordinator))

        # All tools should share the same registry we provided
        for tool in coordinator._mounted_tools.values():
            assert tool._registry is registry

    def test_mount_creates_registry_if_missing(self) -> None:
        """mount() creates a standalone registry if no capability is set."""
        from amplifier_module_tools_env_all import mount

        coordinator = MockCoordinator()
        # Intentionally NOT setting env_registry capability

        asyncio.run(mount(coordinator))

        # Should still register 11 tools
        assert len(coordinator._mounted_tools) == 11

        # Should have created and stored a registry as capability
        registry = coordinator.get_capability("env_registry")
        assert registry is not None
        assert isinstance(registry, EnvironmentRegistry)

        # The fallback registry should have "local" registered
        instances = registry.list_instances()
        local_names = [i["name"] for i in instances]
        assert "local" in local_names

    def test_tool_names_are_correct(self) -> None:
        """All 11 expected tool names are registered."""
        from amplifier_module_tools_env_all import mount

        coordinator = MockCoordinator()
        registry = EnvironmentRegistry()
        registry.register("local", LocalBackend(working_dir="/tmp"), "local")
        coordinator.register_capability("env_registry", registry)

        asyncio.run(mount(coordinator))

        actual_names = sorted(coordinator._mounted_tools.keys())
        assert actual_names == EXPECTED_TOOL_NAMES

    def test_mount_returns_metadata(self) -> None:
        """mount() returns dict with name, version, description, and tool list."""
        from amplifier_module_tools_env_all import mount

        coordinator = MockCoordinator()
        registry = EnvironmentRegistry()
        registry.register("local", LocalBackend(working_dir="/tmp"), "local")
        coordinator.register_capability("env_registry", registry)

        result = asyncio.run(mount(coordinator))

        assert result["name"] == "tools-env-all"
        assert result["version"] == "0.1.0"
        assert "tools" in result
        assert sorted(result["tools"]) == EXPECTED_TOOL_NAMES
