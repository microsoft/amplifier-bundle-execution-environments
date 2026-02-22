"""env_destroy and env_list — environment instance management tools."""

from __future__ import annotations

import json
from typing import Any

from amplifier_core import ToolResult

from amplifier_env_common.registry import EnvironmentRegistry


class EnvDestroyTool:
    """Tear down a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_destroy"

    @property
    def description(self) -> str:
        return "Destroy a named environment instance. Tears down Docker containers, closes SSH connections."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": {
                    "type": "string",
                    "description": "Name of the environment instance to destroy",
                },
            },
            "required": ["instance"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        instance = input.get("instance")
        if not instance:
            return ToolResult(
                success=False,
                error={"message": "Missing required parameter: 'instance'"},
            )

        try:
            await self._registry.destroy(instance)
            return ToolResult(
                success=True, output=f"Destroyed environment '{instance}'."
            )
        except KeyError:
            existing = [i["name"] for i in self._registry.list_instances()]
            return ToolResult(
                success=False,
                error={
                    "message": f"Instance '{instance}' not found. Active: {existing}"
                },
            )


class EnvListTool:
    """List all active environment instances."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_list"

    @property
    def description(self) -> str:
        return "List all active environment instances with their type and status."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        instances = self._registry.list_instances()
        return ToolResult(success=True, output=json.dumps(instances, indent=2))
