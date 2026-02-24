"""Tests for ReadOnlyWrapper — rejects write operations on execution environments."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.protocol import EnvironmentBackend
from amplifier_env_common.wrappers.readonly_wrapper import ReadOnlyWrapper


# ---------------------------------------------------------------------------
# Test fixture: FakeBackend that records calls (same pattern as LoggingWrapper tests)
# ---------------------------------------------------------------------------


class FakeBackend:
    """Implements EnvironmentBackend and records all calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    @property
    def env_type(self) -> str:
        return "fake"

    def working_directory(self) -> str:
        return "/fake/work"

    def platform(self) -> str:
        return "linux"

    def os_version(self) -> str:
        return "FakeOS 1.0"

    async def exec_command(
        self,
        cmd: str,
        timeout: float | None = None,
        workdir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> EnvExecResult:
        self.calls.append(
            (
                "exec_command",
                (cmd,),
                {"timeout": timeout, "workdir": workdir, "env_vars": env_vars},
            )
        )
        return EnvExecResult(stdout="hello", stderr="", exit_code=0, duration_ms=42)

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        self.calls.append(("read_file", (path,), {"offset": offset, "limit": limit}))
        return "file content"

    async def write_file(self, path: str, content: str) -> None:
        self.calls.append(("write_file", (path, content), {}))

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        self.calls.append(("edit_file", (path, old_string, new_string), {}))
        return "replaced 1 occurrence"

    async def file_exists(self, path: str) -> bool:
        self.calls.append(("file_exists", (path,), {}))
        return True

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        self.calls.append(("list_dir", (path,), {"depth": depth}))
        return [EnvFileEntry(name="a.txt", entry_type="file")]

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        self.calls.append(
            (
                "grep",
                (pattern,),
                {
                    "path": path,
                    "glob_filter": glob_filter,
                    "case_insensitive": case_insensitive,
                    "max_results": max_results,
                },
            )
        )
        return "match:1: foo"

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        self.calls.append(("glob_files", (pattern,), {"path": path}))
        return ["a.txt"]

    async def cleanup(self) -> None:
        self.calls.append(("cleanup", (), {}))

    def info(self) -> dict[str, Any]:
        return {"type": "fake", "working_dir": "/fake/work"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """ReadOnlyWrapper must satisfy EnvironmentBackend protocol."""

    def test_satisfies_protocol(self) -> None:
        wrapper = ReadOnlyWrapper(inner=FakeBackend())
        assert isinstance(wrapper, EnvironmentBackend)


class TestWriteRejection:
    """write_file and edit_file must raise PermissionError."""

    def test_write_file_raises_permission_error(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        with pytest.raises(PermissionError, match="read-only"):
            asyncio.run(wrapper.write_file("/tmp/out.txt", "hello"))
        # Must NOT have delegated to inner
        assert len(fake.calls) == 0

    def test_edit_file_raises_permission_error(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        with pytest.raises(PermissionError, match="read-only"):
            asyncio.run(wrapper.edit_file("/tmp/f.py", "old", "new"))
        # Must NOT have delegated to inner
        assert len(fake.calls) == 0


class TestExecPassthrough:
    """exec_command must delegate to inner backend."""

    def test_exec_passes_through(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        result = asyncio.run(
            wrapper.exec_command("echo hi", timeout=10, workdir="/tmp")
        )
        assert result.stdout == "hello"
        assert result.exit_code == 0
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "exec_command"
        assert fake.calls[0][1] == ("echo hi",)
        assert fake.calls[0][2]["timeout"] == 10
        assert fake.calls[0][2]["workdir"] == "/tmp"


class TestReadFilePassthrough:
    """read_file must delegate to inner backend."""

    def test_read_file_passes_through(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        result = asyncio.run(wrapper.read_file("/etc/hosts", offset=5, limit=10))
        assert result == "file content"
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "read_file"
        assert fake.calls[0][1] == ("/etc/hosts",)
        assert fake.calls[0][2] == {"offset": 5, "limit": 10}


class TestFileExistsPassthrough:
    """file_exists must delegate to inner backend."""

    def test_file_exists_passes_through(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        result = asyncio.run(wrapper.file_exists("/tmp/x"))
        assert result is True
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "file_exists"


class TestListDirPassthrough:
    """list_dir must delegate to inner backend."""

    def test_list_dir_passes_through(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        result = asyncio.run(wrapper.list_dir("/tmp", depth=2))
        assert len(result) == 1
        assert result[0].name == "a.txt"
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "list_dir"
        assert fake.calls[0][2]["depth"] == 2


class TestGrepPassthrough:
    """grep must delegate to inner backend."""

    def test_grep_passes_through(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        result = asyncio.run(
            wrapper.grep("TODO", path="/src", case_insensitive=True, max_results=50)
        )
        assert result == "match:1: foo"
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "grep"
        assert fake.calls[0][1] == ("TODO",)
        assert fake.calls[0][2]["path"] == "/src"
        assert fake.calls[0][2]["case_insensitive"] is True
        assert fake.calls[0][2]["max_results"] == 50


class TestGlobPassthrough:
    """glob_files must delegate to inner backend."""

    def test_glob_passes_through(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        result = asyncio.run(wrapper.glob_files("*.py", path="/src"))
        assert result == ["a.txt"]
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "glob_files"
        assert fake.calls[0][1] == ("*.py",)
        assert fake.calls[0][2]["path"] == "/src"


class TestCleanupPassthrough:
    """cleanup must delegate to inner backend."""

    def test_cleanup_passes_through(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        asyncio.run(wrapper.cleanup())
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "cleanup"


class TestMetadataPassthrough:
    """env_type, working_directory, platform, os_version, info all delegate."""

    def test_metadata_passthrough(self) -> None:
        fake = FakeBackend()
        wrapper = ReadOnlyWrapper(inner=fake)
        assert wrapper.env_type == "fake"
        assert wrapper.working_directory() == "/fake/work"
        assert wrapper.platform() == "linux"
        assert wrapper.os_version() == "FakeOS 1.0"
        assert wrapper.info() == {"type": "fake", "working_dir": "/fake/work"}
