"""Tests for the 8 common-shape dispatch tools.

Each tool looks up an instance by name in the registry, then delegates
to the corresponding backend method. Tests use a FakeBackend that records
calls and returns scripted responses.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# FakeBackend — records every call and returns scripted responses
# ---------------------------------------------------------------------------


class FakeBackend:
    """Backend that records calls and returns configurable responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    @property
    def env_type(self) -> str:
        return "fake"

    async def exec_command(
        self, cmd: str, timeout: float | None = None, workdir: str | None = None
    ) -> EnvExecResult:
        self.calls.append(("exec_command", cmd, timeout, workdir))
        return EnvExecResult(stdout="ok\n", stderr="", exit_code=0)

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        self.calls.append(("read_file", path, offset, limit))
        return "file content\n"

    async def write_file(self, path: str, content: str) -> None:
        self.calls.append(("write_file", path, content))

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        self.calls.append(("edit_file", path, old_string, new_string))
        return "Replaced 1 occurrence in /tmp/test.py"

    async def file_exists(self, path: str) -> bool:
        self.calls.append(("file_exists", path))
        return True

    async def list_dir(self, path: str) -> list[EnvFileEntry]:
        self.calls.append(("list_dir", path))
        return [
            EnvFileEntry(name="foo.py", entry_type="file", size=100),
            EnvFileEntry(name="bar", entry_type="dir", size=None),
        ]

    async def grep(
        self, pattern: str, path: str | None = None, glob_filter: str | None = None
    ) -> str:
        self.calls.append(("grep", pattern, path, glob_filter))
        return "src/main.py:10:match\n"

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        self.calls.append(("glob_files", pattern, path))
        return ["src/main.py", "src/util.py"]

    async def cleanup(self) -> None:
        pass

    def info(self) -> dict[str, Any]:
        return {"type": "fake"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def registry(fake_backend: FakeBackend) -> EnvironmentRegistry:
    """Registry with a 'local' instance backed by FakeBackend."""
    reg = EnvironmentRegistry()
    reg.register("local", fake_backend, "fake")
    return reg


@pytest.fixture
def registry_multi(fake_backend: FakeBackend) -> EnvironmentRegistry:
    """Registry with 'local' and 'build' instances."""
    reg = EnvironmentRegistry()
    reg.register("local", fake_backend, "fake")
    reg.register("build", FakeBackend(), "fake")
    return reg


# ---------------------------------------------------------------------------
# Helper: _get_backend
# ---------------------------------------------------------------------------


class TestGetBackendHelper:
    """Tests for the shared _get_backend dispatch helper."""

    def test_returns_backend_for_existing_instance(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import _get_backend

        backend, error = _get_backend(registry, {"instance": "local"})
        assert backend is fake_backend
        assert error is None

    def test_defaults_to_local_when_no_instance(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import _get_backend

        backend, error = _get_backend(registry, {})
        assert backend is fake_backend
        assert error is None

    def test_returns_error_for_missing_instance(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import _get_backend

        backend, error = _get_backend(registry, {"instance": "nonexistent"})
        assert backend is None
        assert error is not None
        assert error.success is False
        assert "nonexistent" in error.error["message"]
        assert "local" in error.error["message"]


# ---------------------------------------------------------------------------
# EnvExecTool
# ---------------------------------------------------------------------------


class TestEnvExecToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvExecTool

        tool = EnvExecTool(registry)
        assert tool.name == "env_exec"


class TestEnvExecToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvExecTool

        tool = EnvExecTool(registry)
        result = asyncio.run(
            tool.execute({"command": "ls -la", "timeout": 30, "workdir": "/tmp"})
        )
        assert result.success is True
        assert result.output["stdout"] == "ok\n"
        assert result.output["exit_code"] == 0
        assert fake_backend.calls == [("exec_command", "ls -la", 30, "/tmp")]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvExecTool

        tool = EnvExecTool(registry)
        result = asyncio.run(tool.execute({"command": "echo hi"}))
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvExecTool

        tool = EnvExecTool(registry)
        result = asyncio.run(tool.execute({"instance": "ghost", "command": "echo"}))
        assert result.success is False
        assert "ghost" in result.error["message"]

    def test_missing_required_param_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvExecTool

        tool = EnvExecTool(registry)
        result = asyncio.run(tool.execute({}))
        assert result.success is False
        assert "command" in result.error["message"].lower()

    def test_backend_exception_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvExecTool

        # Replace backend exec_command with one that raises
        backend = registry.get("local")

        async def _boom(cmd, timeout=None, workdir=None):
            raise RuntimeError("connection lost")

        backend.exec_command = _boom  # type: ignore[attr-defined]

        tool = EnvExecTool(registry)
        result = asyncio.run(tool.execute({"command": "echo"}))
        assert result.success is False
        assert "connection lost" in result.error["message"]


# ---------------------------------------------------------------------------
# EnvReadFileTool
# ---------------------------------------------------------------------------


class TestEnvReadFileToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvReadFileTool

        tool = EnvReadFileTool(registry)
        assert tool.name == "env_read_file"


class TestEnvReadFileToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvReadFileTool

        tool = EnvReadFileTool(registry)
        result = asyncio.run(
            tool.execute({"path": "/tmp/test.py", "offset": 10, "limit": 50})
        )
        assert result.success is True
        assert result.output == "file content\n"
        assert fake_backend.calls == [("read_file", "/tmp/test.py", 10, 50)]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvReadFileTool

        tool = EnvReadFileTool(registry)
        result = asyncio.run(tool.execute({"path": "/tmp/f.txt"}))
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvReadFileTool

        tool = EnvReadFileTool(registry)
        result = asyncio.run(tool.execute({"instance": "nope", "path": "/tmp/f.txt"}))
        assert result.success is False
        assert "nope" in result.error["message"]

    def test_missing_required_param_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvReadFileTool

        tool = EnvReadFileTool(registry)
        result = asyncio.run(tool.execute({}))
        assert result.success is False
        assert "path" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# EnvWriteFileTool
# ---------------------------------------------------------------------------


class TestEnvWriteFileToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvWriteFileTool

        tool = EnvWriteFileTool(registry)
        assert tool.name == "env_write_file"


class TestEnvWriteFileToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvWriteFileTool

        tool = EnvWriteFileTool(registry)
        result = asyncio.run(
            tool.execute({"path": "/tmp/out.txt", "content": "hello world"})
        )
        assert result.success is True
        assert fake_backend.calls == [("write_file", "/tmp/out.txt", "hello world")]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvWriteFileTool

        tool = EnvWriteFileTool(registry)
        result = asyncio.run(tool.execute({"path": "/tmp/f.txt", "content": "x"}))
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvWriteFileTool

        tool = EnvWriteFileTool(registry)
        result = asyncio.run(
            tool.execute({"instance": "nope", "path": "/tmp/f.txt", "content": "x"})
        )
        assert result.success is False
        assert "nope" in result.error["message"]

    def test_missing_path_returns_error(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvWriteFileTool

        tool = EnvWriteFileTool(registry)
        result = asyncio.run(tool.execute({"content": "hello"}))
        assert result.success is False
        assert "path" in result.error["message"].lower()

    def test_missing_content_returns_error(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvWriteFileTool

        tool = EnvWriteFileTool(registry)
        result = asyncio.run(tool.execute({"path": "/tmp/f.txt"}))
        assert result.success is False
        assert "content" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# EnvEditFileTool
# ---------------------------------------------------------------------------


class TestEnvEditFileToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvEditFileTool

        tool = EnvEditFileTool(registry)
        assert tool.name == "env_edit_file"


class TestEnvEditFileToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvEditFileTool

        tool = EnvEditFileTool(registry)
        result = asyncio.run(
            tool.execute(
                {
                    "path": "/tmp/test.py",
                    "old_string": "foo",
                    "new_string": "bar",
                }
            )
        )
        assert result.success is True
        assert fake_backend.calls == [("edit_file", "/tmp/test.py", "foo", "bar")]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvEditFileTool

        tool = EnvEditFileTool(registry)
        result = asyncio.run(
            tool.execute({"path": "/tmp/f.py", "old_string": "a", "new_string": "b"})
        )
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvEditFileTool

        tool = EnvEditFileTool(registry)
        result = asyncio.run(
            tool.execute(
                {
                    "instance": "nope",
                    "path": "/f.py",
                    "old_string": "a",
                    "new_string": "b",
                }
            )
        )
        assert result.success is False
        assert "nope" in result.error["message"]

    def test_missing_path_returns_error(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvEditFileTool

        tool = EnvEditFileTool(registry)
        result = asyncio.run(tool.execute({"old_string": "a", "new_string": "b"}))
        assert result.success is False
        assert "path" in result.error["message"].lower()

    def test_missing_old_string_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvEditFileTool

        tool = EnvEditFileTool(registry)
        result = asyncio.run(tool.execute({"path": "/f.py", "new_string": "b"}))
        assert result.success is False
        assert "old_string" in result.error["message"].lower()

    def test_missing_new_string_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvEditFileTool

        tool = EnvEditFileTool(registry)
        result = asyncio.run(tool.execute({"path": "/f.py", "old_string": "a"}))
        assert result.success is False
        assert "new_string" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# EnvGrepTool
# ---------------------------------------------------------------------------


class TestEnvGrepToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGrepTool

        tool = EnvGrepTool(registry)
        assert tool.name == "env_grep"


class TestEnvGrepToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGrepTool

        tool = EnvGrepTool(registry)
        result = asyncio.run(
            tool.execute({"pattern": "TODO", "path": "src/", "glob": "*.py"})
        )
        assert result.success is True
        assert result.output == "src/main.py:10:match\n"
        assert fake_backend.calls == [("grep", "TODO", "src/", "*.py")]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGrepTool

        tool = EnvGrepTool(registry)
        result = asyncio.run(tool.execute({"pattern": "TODO"}))
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGrepTool

        tool = EnvGrepTool(registry)
        result = asyncio.run(tool.execute({"instance": "nope", "pattern": "TODO"}))
        assert result.success is False
        assert "nope" in result.error["message"]

    def test_missing_required_param_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGrepTool

        tool = EnvGrepTool(registry)
        result = asyncio.run(tool.execute({}))
        assert result.success is False
        assert "pattern" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# EnvGlobTool
# ---------------------------------------------------------------------------


class TestEnvGlobToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGlobTool

        tool = EnvGlobTool(registry)
        assert tool.name == "env_glob"


class TestEnvGlobToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGlobTool

        tool = EnvGlobTool(registry)
        result = asyncio.run(tool.execute({"pattern": "**/*.py", "path": "src/"}))
        assert result.success is True
        assert result.output == ["src/main.py", "src/util.py"]
        assert fake_backend.calls == [("glob_files", "**/*.py", "src/")]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGlobTool

        tool = EnvGlobTool(registry)
        result = asyncio.run(tool.execute({"pattern": "*.py"}))
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGlobTool

        tool = EnvGlobTool(registry)
        result = asyncio.run(tool.execute({"instance": "nope", "pattern": "*.py"}))
        assert result.success is False
        assert "nope" in result.error["message"]

    def test_missing_required_param_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvGlobTool

        tool = EnvGlobTool(registry)
        result = asyncio.run(tool.execute({}))
        assert result.success is False
        assert "pattern" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# EnvListDirTool
# ---------------------------------------------------------------------------


class TestEnvListDirToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvListDirTool

        tool = EnvListDirTool(registry)
        assert tool.name == "env_list_dir"


class TestEnvListDirToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvListDirTool

        tool = EnvListDirTool(registry)
        result = asyncio.run(tool.execute({"path": "/tmp"}))
        assert result.success is True
        # Output should be serialized list of entries
        entries = result.output
        assert len(entries) == 2
        assert entries[0]["name"] == "foo.py"
        assert entries[1]["entry_type"] == "dir"
        assert fake_backend.calls == [("list_dir", "/tmp")]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvListDirTool

        tool = EnvListDirTool(registry)
        result = asyncio.run(tool.execute({}))
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_defaults_path_to_dot(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvListDirTool

        tool = EnvListDirTool(registry)
        asyncio.run(tool.execute({}))
        assert fake_backend.calls == [("list_dir", ".")]

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvListDirTool

        tool = EnvListDirTool(registry)
        result = asyncio.run(tool.execute({"instance": "nope"}))
        assert result.success is False
        assert "nope" in result.error["message"]


# ---------------------------------------------------------------------------
# EnvFileExistsTool
# ---------------------------------------------------------------------------


class TestEnvFileExistsToolName:
    def test_name(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvFileExistsTool

        tool = EnvFileExistsTool(registry)
        assert tool.name == "env_file_exists"


class TestEnvFileExistsToolDispatch:
    def test_dispatches_to_backend(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvFileExistsTool

        tool = EnvFileExistsTool(registry)
        result = asyncio.run(tool.execute({"path": "/tmp/test.py"}))
        assert result.success is True
        assert result.output["exists"] is True
        assert fake_backend.calls == [("file_exists", "/tmp/test.py")]

    def test_default_instance_is_local(
        self, registry: EnvironmentRegistry, fake_backend: FakeBackend
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvFileExistsTool

        tool = EnvFileExistsTool(registry)
        result = asyncio.run(tool.execute({"path": "/tmp/f.txt"}))
        assert result.success is True
        assert len(fake_backend.calls) == 1

    def test_missing_instance_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvFileExistsTool

        tool = EnvFileExistsTool(registry)
        result = asyncio.run(tool.execute({"instance": "nope", "path": "/tmp/f.txt"}))
        assert result.success is False
        assert "nope" in result.error["message"]

    def test_missing_required_param_returns_error(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import EnvFileExistsTool

        tool = EnvFileExistsTool(registry)
        result = asyncio.run(tool.execute({}))
        assert result.success is False
        assert "path" in result.error["message"].lower()


# ---------------------------------------------------------------------------
# Cross-cutting: all 8 tools have "instance" in schema
# ---------------------------------------------------------------------------


class TestAllToolsHaveInstanceParam:
    def test_all_tools_have_instance_in_schema(
        self, registry: EnvironmentRegistry
    ) -> None:
        from amplifier_module_tools_env_all.dispatch import (
            EnvEditFileTool,
            EnvExecTool,
            EnvFileExistsTool,
            EnvGlobTool,
            EnvGrepTool,
            EnvListDirTool,
            EnvReadFileTool,
            EnvWriteFileTool,
        )

        tool_classes = [
            EnvExecTool,
            EnvReadFileTool,
            EnvWriteFileTool,
            EnvEditFileTool,
            EnvGrepTool,
            EnvGlobTool,
            EnvListDirTool,
            EnvFileExistsTool,
        ]
        for cls in tool_classes:
            tool = cls(registry)
            schema = tool.input_schema
            assert "instance" in schema["properties"], (
                f"{cls.__name__} missing 'instance' in schema"
            )

    def test_all_tools_have_description(self, registry: EnvironmentRegistry) -> None:
        from amplifier_module_tools_env_all.dispatch import (
            EnvEditFileTool,
            EnvExecTool,
            EnvFileExistsTool,
            EnvGlobTool,
            EnvGrepTool,
            EnvListDirTool,
            EnvReadFileTool,
            EnvWriteFileTool,
        )

        tool_classes = [
            EnvExecTool,
            EnvReadFileTool,
            EnvWriteFileTool,
            EnvEditFileTool,
            EnvGrepTool,
            EnvGlobTool,
            EnvListDirTool,
            EnvFileExistsTool,
        ]
        for cls in tool_classes:
            tool = cls(registry)
            assert isinstance(tool.description, str)
            assert len(tool.description) > 10, f"{cls.__name__} description too short"

    def test_instance_not_required_for_any_tool(
        self, registry: EnvironmentRegistry
    ) -> None:
        """Instance param should be optional (defaults to 'local')."""
        from amplifier_module_tools_env_all.dispatch import (
            EnvEditFileTool,
            EnvExecTool,
            EnvFileExistsTool,
            EnvGlobTool,
            EnvGrepTool,
            EnvListDirTool,
            EnvReadFileTool,
            EnvWriteFileTool,
        )

        tool_classes = [
            EnvExecTool,
            EnvReadFileTool,
            EnvWriteFileTool,
            EnvEditFileTool,
            EnvGrepTool,
            EnvGlobTool,
            EnvListDirTool,
            EnvFileExistsTool,
        ]
        for cls in tool_classes:
            tool = cls(registry)
            schema = tool.input_schema
            required = schema.get("required", [])
            assert "instance" not in required, (
                f"{cls.__name__} should not require 'instance'"
            )
