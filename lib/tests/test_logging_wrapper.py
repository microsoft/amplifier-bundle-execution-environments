"""Tests for LoggingWrapper — composable logging for execution environments."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.protocol import EnvironmentBackend
from amplifier_env_common.wrappers.logging_wrapper import LoggingWrapper


# ---------------------------------------------------------------------------
# Test fixture: FakeBackend that records calls
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
    """LoggingWrapper must satisfy EnvironmentBackend protocol."""

    def test_satisfies_protocol(self) -> None:
        wrapper = LoggingWrapper(inner=FakeBackend())
        assert isinstance(wrapper, EnvironmentBackend)


class TestExecCommand:
    """exec_command delegation and logging."""

    def test_exec_delegates_to_inner(self) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake)
        result = asyncio.run(
            wrapper.exec_command("echo hi", timeout=10, workdir="/tmp")
        )
        assert result.stdout == "hello"
        assert result.exit_code == 0
        assert result.duration_ms == 42
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "exec_command"
        assert fake.calls[0][1] == ("echo hi",)
        assert fake.calls[0][2]["timeout"] == 10
        assert fake.calls[0][2]["workdir"] == "/tmp"

    def test_exec_logs_command_and_result(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            asyncio.run(wrapper.exec_command("echo hi"))
        # Should have log entries mentioning the command and exit code
        messages = [r.message for r in caplog.records if r.name == "test.env"]
        assert any("echo hi" in m for m in messages), (
            f"Expected 'echo hi' in log messages: {messages}"
        )
        assert any("exit 0" in m for m in messages), (
            f"Expected 'exit 0' in log messages: {messages}"
        )


class TestReadFile:
    """read_file delegation and logging."""

    def test_read_delegates(self) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake)
        result = asyncio.run(wrapper.read_file("/etc/hosts", offset=5, limit=10))
        assert result == "file content"
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "read_file"
        assert fake.calls[0][1] == ("/etc/hosts",)
        assert fake.calls[0][2] == {"offset": 5, "limit": 10}

    def test_read_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            asyncio.run(wrapper.read_file("/etc/hosts"))
        messages = [r.message for r in caplog.records if r.name == "test.env"]
        assert any("/etc/hosts" in m for m in messages)
        # Verify it's at DEBUG level
        levels = [r.levelno for r in caplog.records if r.name == "test.env"]
        assert logging.DEBUG in levels


class TestWriteFile:
    """write_file delegation and logging."""

    def test_write_delegates_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            asyncio.run(wrapper.write_file("/tmp/out.txt", "hello world"))
        # Delegated
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "write_file"
        assert fake.calls[0][1] == ("/tmp/out.txt", "hello world")
        # Logged path and length
        messages = [r.message for r in caplog.records if r.name == "test.env"]
        assert any("/tmp/out.txt" in m for m in messages)
        assert any("11" in m for m in messages), (
            f"Expected char count '11' in log: {messages}"
        )


class TestEditFile:
    """edit_file delegation and logging."""

    def test_edit_delegates_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            result = asyncio.run(wrapper.edit_file("/tmp/f.py", "old", "new"))
        assert result == "replaced 1 occurrence"
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "edit_file"
        # Logged path
        messages = [r.message for r in caplog.records if r.name == "test.env"]
        assert any("/tmp/f.py" in m for m in messages)


class TestSilentOperations:
    """file_exists, list_dir, glob_files should NOT be logged."""

    def test_file_exists_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            result = asyncio.run(wrapper.file_exists("/tmp/x"))
        assert result is True
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "file_exists"
        env_records = [r for r in caplog.records if r.name == "test.env"]
        assert len(env_records) == 0, f"file_exists should not log, got: {env_records}"

    def test_list_dir_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            result = asyncio.run(wrapper.list_dir("/tmp", depth=2))
        assert len(result) == 1
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "list_dir"
        env_records = [r for r in caplog.records if r.name == "test.env"]
        assert len(env_records) == 0, f"list_dir should not log, got: {env_records}"

    def test_glob_files_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            result = asyncio.run(wrapper.glob_files("*.py", path="/src"))
        assert result == ["a.txt"]
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "glob_files"
        env_records = [r for r in caplog.records if r.name == "test.env"]
        assert len(env_records) == 0, f"glob_files should not log, got: {env_records}"


class TestGrep:
    """grep delegation and logging."""

    def test_grep_delegates_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            result = asyncio.run(
                wrapper.grep("TODO", path="/src", case_insensitive=True)
            )
        assert result == "match:1: foo"
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "grep"
        messages = [r.message for r in caplog.records if r.name == "test.env"]
        assert any("TODO" in m for m in messages)


class TestCleanup:
    """cleanup delegation and logging."""

    def test_cleanup_delegates_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake, logger_name="test.env")
        with caplog.at_level(logging.DEBUG, logger="test.env"):
            asyncio.run(wrapper.cleanup())
        assert len(fake.calls) == 1
        assert fake.calls[0][0] == "cleanup"
        messages = [r.message for r in caplog.records if r.name == "test.env"]
        assert any("cleanup" in m for m in messages)


class TestMetadataPassthrough:
    """env_type, working_directory, platform, os_version, info all delegate."""

    def test_metadata_passthrough(self) -> None:
        fake = FakeBackend()
        wrapper = LoggingWrapper(inner=fake)
        assert wrapper.env_type == "fake"
        assert wrapper.working_directory() == "/fake/work"
        assert wrapper.platform() == "linux"
        assert wrapper.os_version() == "FakeOS 1.0"
        assert wrapper.info() == {"type": "fake", "working_dir": "/fake/work"}
