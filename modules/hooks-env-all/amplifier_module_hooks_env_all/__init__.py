"""Session cleanup hook for instance-based execution environments.

Registers for session:end to call registry.destroy_all(), tearing down
all Docker containers and SSH connections. Prevents resource leaks.

This is the hooks module for the env-all bundle. It shares the
EnvironmentRegistry with the tools module via coordinator capabilities.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from amplifier_core import HookResult

from amplifier_env_common.backends.local import LocalBackend
from amplifier_env_common.registry import EnvironmentRegistry

logger = logging.getLogger(__name__)


class EnvCleanupHandler:
    """Destroys all environment instances at session end."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    async def handle_session_end(self, event: str, data: dict[str, Any]) -> HookResult:
        """Destroy all non-persistent instances."""
        session_id = data.get("session_id", "unknown")
        instances = self._registry.list_instances()

        if not instances:
            logger.info(
                "env-cleanup: no instances to clean up for session %s", session_id
            )
            return HookResult(action="continue")

        logger.info(
            "env-cleanup: destroying %d instances for session %s",
            len(instances),
            session_id,
        )

        try:
            await self._registry.destroy_all()
        except Exception:
            logger.warning(
                "env-cleanup: some instances failed to clean up for session %s",
                session_id,
                exc_info=True,
            )

        return HookResult(action="continue")


async def mount(
    coordinator: Any, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Mount the session cleanup hook.

    Creates an EnvironmentRegistry, registers the "local" default instance,
    stores the registry as a coordinator capability for the tools module,
    and registers the session:end cleanup hook.
    """
    config = config or {}

    # Create the shared registry
    registry = EnvironmentRegistry()

    # Auto-create the "local" instance
    working_dir = config.get("working_dir", os.getcwd())
    local_backend = LocalBackend(working_dir=working_dir)
    registry.register("local", local_backend, "local")

    # Store registry as a capability for the tools module
    coordinator.register_capability("env_registry", registry)

    # Register cleanup handler
    handler = EnvCleanupHandler(registry)
    coordinator.hooks.register(
        "session:end",
        handler.handle_session_end,
        priority=90,  # Late — clean up after everything else
        name="env-instance-cleanup",
    )

    return {
        "name": "hooks-env-all",
        "version": "0.1.0",
        "description": "Session cleanup for instance-based execution environments",
    }
