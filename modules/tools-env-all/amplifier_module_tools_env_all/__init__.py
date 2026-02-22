"""Instance-based execution environment tools for Amplifier.

Provides 11 tools:
- env_create: Factory for creating environment instances
- env_destroy: Tear down instances
- env_list: Show all active instances
- env_exec, env_read_file, env_write_file, env_edit_file,
  env_grep, env_glob, env_list_dir, env_file_exists: Common-shape dispatch tools
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def mount(
    coordinator: Any, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Mount all 11 instance-based environment tools.

    Retrieves the shared EnvironmentRegistry from coordinator capabilities
    (created by hooks-env-all at session start) and registers all tools.
    """
    from amplifier_env_common.registry import EnvironmentRegistry

    from .dispatch import (
        EnvEditFileTool,
        EnvExecTool,
        EnvFileExistsTool,
        EnvGlobTool,
        EnvGrepTool,
        EnvListDirTool,
        EnvReadFileTool,
        EnvWriteFileTool,
    )
    from .factory import EnvCreateTool
    from .management import EnvDestroyTool, EnvListTool

    config = config or {}

    # Get-or-create shared registry (handles mount ordering — hooks may mount after tools)
    registry = coordinator.get_capability("env_registry")
    if registry is None:
        import os

        from amplifier_env_common.backends.local import LocalBackend

        registry = EnvironmentRegistry()
        registry.register("local", LocalBackend(working_dir=os.getcwd()), "local")
        coordinator.register_capability("env_registry", registry)
        logger.info("tools-env-all: created shared registry with 'local' instance")
    else:
        logger.info("tools-env-all: using existing registry from hooks module")

    # Create all 11 tools
    all_tools = [
        EnvCreateTool(registry=registry, coordinator=coordinator),
        EnvDestroyTool(registry=registry),
        EnvListTool(registry=registry),
        EnvExecTool(registry=registry),
        EnvReadFileTool(registry=registry),
        EnvWriteFileTool(registry=registry),
        EnvEditFileTool(registry=registry),
        EnvGrepTool(registry=registry),
        EnvGlobTool(registry=registry),
        EnvListDirTool(registry=registry),
        EnvFileExistsTool(registry=registry),
    ]

    # Register all tools with coordinator
    for tool in all_tools:
        await coordinator.mount("tools", tool, name=tool.name)

    logger.info("tools-env-all: registered %d tools", len(all_tools))

    return {
        "name": "tools-env-all",
        "version": "0.1.0",
        "description": "Instance-based execution environment tools (11 tools)",
        "tools": [t.name for t in all_tools],
    }
