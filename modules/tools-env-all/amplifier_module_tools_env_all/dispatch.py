"""8 common-shape dispatch tools routing operations through the registry.

Each tool looks up a backend instance by name, then delegates to the
corresponding EnvironmentBackend method. All tools accept an optional
``instance`` parameter that defaults to "local".
"""

from __future__ import annotations

from typing import Any

from amplifier_core import ToolResult

from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# Shared dispatch helper
# ---------------------------------------------------------------------------


def _get_backend(
    registry: EnvironmentRegistry, input: dict[str, Any]
) -> tuple[Any, ToolResult | None]:
    """Look up backend by instance name; return (backend, None) or (None, error)."""
    instance = input.get("instance", "local")
    backend = registry.get(instance)
    if backend is None:
        existing = [i["name"] for i in registry.list_instances()]
        return None, ToolResult(
            success=False,
            error={"message": f"Instance '{instance}' not found. Active: {existing}"},
        )
    return backend, None


def _missing(param: str) -> ToolResult:
    """Return a standard 'missing required parameter' error."""
    return ToolResult(
        success=False, error={"message": f"Missing required parameter: '{param}'"}
    )


# ---------------------------------------------------------------------------
# Shared schema fragment
# ---------------------------------------------------------------------------

_INSTANCE_SCHEMA = {
    "type": "string",
    "description": "Environment instance name (default: 'local')",
}


# ---------------------------------------------------------------------------
# EnvExecTool
# ---------------------------------------------------------------------------


class EnvExecTool:
    """Execute a shell command in a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_exec"

    @property
    def description(self) -> str:
        return "Execute a shell command in a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
                "workdir": {"type": "string", "description": "Working directory"},
                "env_vars": {
                    "type": "object",
                    "description": "Environment variables to set (additive merge)",
                },
            },
            "required": ["command"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        command = input.get("command")
        if not command:
            return _missing("command")
        try:
            result = await backend.exec_command(
                command,
                timeout=input.get("timeout"),
                workdir=input.get("workdir"),
                env_vars=input.get("env_vars"),
            )
            return ToolResult(
                success=True,
                output={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "duration_ms": result.duration_ms,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})


# ---------------------------------------------------------------------------
# EnvReadFileTool
# ---------------------------------------------------------------------------


class EnvReadFileTool:
    """Read file content from a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_read_file"

    @property
    def description(self) -> str:
        return "Read file content from a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "path": {"type": "string", "description": "File path to read"},
                "offset": {"type": "integer", "description": "Line offset (1-based)"},
                "limit": {"type": "integer", "description": "Max lines to read"},
            },
            "required": ["path"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        path = input.get("path")
        if not path:
            return _missing("path")
        try:
            content = await backend.read_file(
                path, offset=input.get("offset"), limit=input.get("limit")
            )
            return ToolResult(success=True, output=content)
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})


# ---------------------------------------------------------------------------
# EnvWriteFileTool
# ---------------------------------------------------------------------------


class EnvWriteFileTool:
    """Write content to a file in a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_write_file"

    @property
    def description(self) -> str:
        return "Write content to a file in a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        path = input.get("path")
        if not path:
            return _missing("path")
        content = input.get("content")
        if content is None:
            return _missing("content")
        try:
            await backend.write_file(path, content)
            return ToolResult(success=True, output=f"Written to {path}")
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})


# ---------------------------------------------------------------------------
# EnvEditFileTool
# ---------------------------------------------------------------------------


class EnvEditFileTool:
    """Edit a file by replacing an exact string match in a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing an exact string match in a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "path": {"type": "string", "description": "File path to edit"},
                "old_string": {"type": "string", "description": "Exact string to find"},
                "new_string": {"type": "string", "description": "Replacement string"},
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        path = input.get("path")
        if not path:
            return _missing("path")
        old_string = input.get("old_string")
        if old_string is None:
            return _missing("old_string")
        new_string = input.get("new_string")
        if new_string is None:
            return _missing("new_string")
        try:
            msg = await backend.edit_file(path, old_string, new_string)
            return ToolResult(success=True, output=msg)
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})


# ---------------------------------------------------------------------------
# EnvGrepTool
# ---------------------------------------------------------------------------


class EnvGrepTool:
    """Search file contents with regex in a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_grep"

    @property
    def description(self) -> str:
        return "Search file contents with regex in a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case-insensitive search (default: false)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matches to return",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        pattern = input.get("pattern")
        if not pattern:
            return _missing("pattern")
        try:
            matches = await backend.grep(
                pattern,
                path=input.get("path"),
                glob_filter=input.get("glob"),
                case_insensitive=input.get("case_insensitive", False),
                max_results=input.get("max_results"),
            )
            return ToolResult(success=True, output=matches)
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})


# ---------------------------------------------------------------------------
# EnvGlobTool
# ---------------------------------------------------------------------------


class EnvGlobTool:
    """Find files matching a glob pattern in a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_glob"

    @property
    def description(self) -> str:
        return "Find files matching a glob pattern in a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "pattern": {"type": "string", "description": "Glob pattern to match"},
                "path": {
                    "type": "string",
                    "description": "Base directory to search from",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        pattern = input.get("pattern")
        if not pattern:
            return _missing("pattern")
        try:
            files = await backend.glob_files(pattern, path=input.get("path"))
            return ToolResult(success=True, output=files)
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})


# ---------------------------------------------------------------------------
# EnvListDirTool
# ---------------------------------------------------------------------------


class EnvListDirTool:
    """List directory contents in a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_list_dir"

    @property
    def description(self) -> str:
        return "List directory contents in a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "path": {"type": "string", "description": "Directory path to list"},
                "depth": {
                    "type": "integer",
                    "description": "Directory depth (default: 1, immediate children only)",
                },
            },
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        path = input.get("path", ".")
        try:
            entries = await backend.list_dir(path, depth=input.get("depth", 1))
            return ToolResult(
                success=True,
                output=[e.model_dump() for e in entries],
            )
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})


# ---------------------------------------------------------------------------
# EnvFileExistsTool
# ---------------------------------------------------------------------------


class EnvFileExistsTool:
    """Check if a file or directory exists in a named environment instance."""

    def __init__(self, registry: EnvironmentRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "env_file_exists"

    @property
    def description(self) -> str:
        return "Check if a file or directory exists in a named environment instance."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instance": _INSTANCE_SCHEMA,
                "path": {"type": "string", "description": "Path to check"},
            },
            "required": ["path"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        backend, error = _get_backend(self._registry, input)
        if error:
            return error
        path = input.get("path")
        if not path:
            return _missing("path")
        try:
            exists = await backend.file_exists(path)
            return ToolResult(success=True, output={"exists": exists, "path": path})
        except Exception as e:
            return ToolResult(success=False, error={"message": str(e)})
