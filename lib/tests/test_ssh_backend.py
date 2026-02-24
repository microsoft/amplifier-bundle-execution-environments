"""Tests for SSHBackendWrapper — wraps SSH exec function into EnvironmentBackend."""

from __future__ import annotations

import pytest

from amplifier_env_common.backends.ssh import SSHBackendWrapper
from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.protocol import EnvironmentBackend


# ---------------------------------------------------------------------------
# Mock exec function
# ---------------------------------------------------------------------------


class MockExecFn:
    """Records calls and returns scripted responses for SSH exec."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses: list[EnvExecResult] = []

    def add_response(
        self, stdout: str = "", stderr: str = "", exit_code: int = 0
    ) -> None:
        self.responses.append(
            EnvExecResult(stdout=stdout, stderr=stderr, exit_code=exit_code)
        )

    async def __call__(self, cmd: str, timeout: float | None = None) -> EnvExecResult:
        self.calls.append({"cmd": cmd, "timeout": timeout})
        if self.responses:
            return self.responses.pop(0)
        return EnvExecResult(stdout="", stderr="", exit_code=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_exec():
    return MockExecFn()


@pytest.fixture
def backend(mock_exec):
    return SSHBackendWrapper(
        exec_fn=mock_exec,
        host="test-host.example.com",
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """SSHBackendWrapper must satisfy the EnvironmentBackend protocol."""

    def test_isinstance_check(self, backend):
        assert isinstance(backend, EnvironmentBackend)

    def test_env_type_is_ssh(self, backend):
        assert backend.env_type == "ssh"


# ---------------------------------------------------------------------------
# exec_command
# ---------------------------------------------------------------------------


class TestExecCommand:
    """exec_command passes command through the exec function."""

    @pytest.mark.asyncio
    async def test_passes_command_through(self, backend, mock_exec):
        mock_exec.add_response(stdout="hello\n", stderr="", exit_code=0)
        result = await backend.exec_command("echo hello")
        assert isinstance(result, EnvExecResult)
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_captures_stderr_and_exit_code(self, backend, mock_exec):
        mock_exec.add_response(stdout="", stderr="error msg", exit_code=1)
        result = await backend.exec_command("failing_cmd")
        assert result.stderr == "error msg"
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_records_command(self, backend, mock_exec):
        mock_exec.add_response(stdout="ok")
        await backend.exec_command("ls -la")
        assert len(mock_exec.calls) == 1
        assert mock_exec.calls[0]["cmd"] == "ls -la"

    @pytest.mark.asyncio
    async def test_passes_timeout(self, backend, mock_exec):
        mock_exec.add_response()
        await backend.exec_command("pwd", timeout=30.0)
        assert mock_exec.calls[0]["timeout"] == 30.0

    @pytest.mark.asyncio
    async def test_workdir_prepends_cd(self, backend, mock_exec):
        mock_exec.add_response()
        await backend.exec_command("pwd", workdir="/tmp/mydir")
        cmd = mock_exec.calls[0]["cmd"]
        assert cmd.startswith("cd ")
        assert "/tmp/mydir" in cmd
        assert "pwd" in cmd

    @pytest.mark.asyncio
    async def test_workdir_with_spaces_is_quoted(self, backend, mock_exec):
        mock_exec.add_response()
        await backend.exec_command("ls", workdir="/tmp/my dir")
        cmd = mock_exec.calls[0]["cmd"]
        assert "'/tmp/my dir'" in cmd

    @pytest.mark.asyncio
    async def test_no_workdir_sends_raw_command(self, backend, mock_exec):
        mock_exec.add_response()
        await backend.exec_command("echo hi")
        assert mock_exec.calls[0]["cmd"] == "echo hi"


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    """read_file translates to cat command."""

    @pytest.mark.asyncio
    async def test_simple_cat(self, backend, mock_exec):
        mock_exec.add_response(stdout="file content\n")
        content = await backend.read_file("/home/user/hello.txt")
        assert content == "file content\n"
        cmd = mock_exec.calls[0]["cmd"]
        assert "cat" in cmd
        assert "/home/user/hello.txt" in cmd

    @pytest.mark.asyncio
    async def test_with_offset_and_limit(self, backend, mock_exec):
        mock_exec.add_response(stdout="line2\nline3\n")
        content = await backend.read_file("/home/user/f.txt", offset=2, limit=2)
        assert content == "line2\nline3\n"
        cmd = mock_exec.calls[0]["cmd"]
        assert "tail -n +2" in cmd
        assert "head -n 2" in cmd

    @pytest.mark.asyncio
    async def test_with_offset_only(self, backend, mock_exec):
        mock_exec.add_response(stdout="line2\nline3\n")
        content = await backend.read_file("/home/user/f.txt", offset=2)
        assert content == "line2\nline3\n"
        cmd = mock_exec.calls[0]["cmd"]
        assert "tail -n +2" in cmd

    @pytest.mark.asyncio
    async def test_with_limit_only(self, backend, mock_exec):
        mock_exec.add_response(stdout="line1\n")
        content = await backend.read_file("/home/user/f.txt", limit=1)
        assert content == "line1\n"
        cmd = mock_exec.calls[0]["cmd"]
        assert "head -n 1" in cmd

    @pytest.mark.asyncio
    async def test_shell_quoting(self, backend, mock_exec):
        """Paths with spaces must be shell-quoted."""
        mock_exec.add_response(stdout="data")
        await backend.read_file("/home/user/my file.txt")
        cmd = mock_exec.calls[0]["cmd"]
        assert "'/home/user/my file.txt'" in cmd


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


class TestWriteFile:
    """write_file translates to mkdir -p + printf."""

    @pytest.mark.asyncio
    async def test_writes_with_printf(self, backend, mock_exec):
        mock_exec.add_response()
        await backend.write_file("/home/user/a/b/out.txt", "hello world")
        cmd = mock_exec.calls[0]["cmd"]
        assert "printf" in cmd
        assert "mkdir -p" in cmd
        assert "/home/user/a/b/out.txt" in cmd

    @pytest.mark.asyncio
    async def test_no_mkdir_for_root_level_file(self, backend, mock_exec):
        """Files without '/' in path skip mkdir -p."""
        mock_exec.add_response()
        await backend.write_file("simple.txt", "content")
        cmd = mock_exec.calls[0]["cmd"]
        assert "printf" in cmd
        assert "mkdir" not in cmd


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------


class TestEditFile:
    """edit_file reads via cat, patches in Python, writes back."""

    @pytest.mark.asyncio
    async def test_read_modify_write(self, backend, mock_exec):
        # Response 1: cat reads existing content
        mock_exec.add_response(stdout="hello world")
        # Response 2: printf writes patched content
        mock_exec.add_response()
        result = await backend.edit_file("/home/user/edit.txt", "hello", "goodbye")
        assert len(mock_exec.calls) == 2
        # First call: cat to read
        assert "cat" in mock_exec.calls[0]["cmd"]
        # Second call: printf to write
        assert "printf" in mock_exec.calls[1]["cmd"]
        assert "Edited" in result or "replaced" in result

    @pytest.mark.asyncio
    async def test_string_not_found_raises(self, backend, mock_exec):
        mock_exec.add_response(stdout="hello world")
        with pytest.raises(ValueError, match="not found"):
            await backend.edit_file("/home/user/edit.txt", "nonexistent", "replacement")

    @pytest.mark.asyncio
    async def test_string_not_unique_raises(self, backend, mock_exec):
        mock_exec.add_response(stdout="aaa bbb aaa")
        with pytest.raises(ValueError, match="not unique"):
            await backend.edit_file("/home/user/edit.txt", "aaa", "ccc")


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExists:
    """file_exists translates to test -e, exit code determines result."""

    @pytest.mark.asyncio
    async def test_exists_returns_true(self, backend, mock_exec):
        mock_exec.add_response(exit_code=0)
        result = await backend.file_exists("/home/user/exists.txt")
        assert result is True
        assert "test -e" in mock_exec.calls[0]["cmd"]

    @pytest.mark.asyncio
    async def test_not_exists_returns_false(self, backend, mock_exec):
        mock_exec.add_response(exit_code=1)
        result = await backend.file_exists("/home/user/nope.txt")
        assert result is False


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


class TestListDir:
    """list_dir translates to ls -1ap and parses output."""

    @pytest.mark.asyncio
    async def test_parses_ls_output(self, backend, mock_exec):
        mock_exec.add_response(stdout="./\n../\nfile.txt\nsubdir/\n")
        entries = await backend.list_dir("/home/user")
        assert isinstance(entries, list)
        assert all(isinstance(e, EnvFileEntry) for e in entries)
        names = {e.name for e in entries}
        assert "file.txt" in names
        assert "subdir" in names
        # . and .. should be filtered out
        assert "." not in names
        assert ".." not in names

    @pytest.mark.asyncio
    async def test_entry_types(self, backend, mock_exec):
        mock_exec.add_response(stdout="readme.md\nsrc/\n")
        entries = await backend.list_dir("/home/user")
        by_name = {e.name: e for e in entries}
        assert by_name["readme.md"].entry_type == "file"
        assert by_name["src"].entry_type == "dir"

    @pytest.mark.asyncio
    async def test_sends_ls_command(self, backend, mock_exec):
        mock_exec.add_response(stdout="")
        await backend.list_dir("/home/user/subdir")
        cmd = mock_exec.calls[0]["cmd"]
        assert "ls -1ap" in cmd
        assert "/home/user/subdir" in cmd


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


class TestGrep:
    """grep translates to grep -rn."""

    @pytest.mark.asyncio
    async def test_finds_matches(self, backend, mock_exec):
        mock_exec.add_response(stdout="/home/user/f.py:1:needle\n")
        result = await backend.grep("needle", path="/home/user")
        assert "needle" in result
        cmd = mock_exec.calls[0]["cmd"]
        assert "grep" in cmd
        assert "-rn" in cmd

    @pytest.mark.asyncio
    async def test_no_match_returns_message(self, backend, mock_exec):
        mock_exec.add_response(stdout="", exit_code=1)
        result = await backend.grep("nonexistent", path="/home/user")
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_glob_filter(self, backend, mock_exec):
        mock_exec.add_response(stdout="match\n")
        await backend.grep("pattern", path="/home/user", glob_filter="*.py")
        cmd = mock_exec.calls[0]["cmd"]
        assert "--include" in cmd
        assert "*.py" in cmd

    @pytest.mark.asyncio
    async def test_default_path_uses_home(self, backend, mock_exec):
        """Without explicit path, grep should use a default search path."""
        mock_exec.add_response(stdout="")
        await backend.grep("pattern")
        cmd = mock_exec.calls[0]["cmd"]
        assert "grep" in cmd
        # Should have some path argument (default .)
        assert "." in cmd or "/" in cmd


# ---------------------------------------------------------------------------
# glob_files
# ---------------------------------------------------------------------------


class TestGlobFiles:
    """glob_files translates to find -name."""

    @pytest.mark.asyncio
    async def test_parses_find_output(self, backend, mock_exec):
        mock_exec.add_response(stdout="/home/user/a.py\n/home/user/sub/b.py\n")
        matches = await backend.glob_files("*.py", path="/home/user")
        assert "/home/user/a.py" in matches
        assert "/home/user/sub/b.py" in matches

    @pytest.mark.asyncio
    async def test_strips_recursive_prefix(self, backend, mock_exec):
        """Patterns like **/*.py should strip **/ for find -name."""
        mock_exec.add_response(stdout="")
        await backend.glob_files("**/*.py", path="/home/user")
        cmd = mock_exec.calls[0]["cmd"]
        assert "find" in cmd
        assert "-name" in cmd
        # The **/ prefix should be stripped since find is already recursive
        assert "**/" not in cmd

    @pytest.mark.asyncio
    async def test_empty_output_returns_empty_list(self, backend, mock_exec):
        mock_exec.add_response(stdout="")
        matches = await backend.glob_files("*.nonexistent", path="/home/user")
        assert matches == []


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    """cleanup calls disconnect_fn if provided."""

    @pytest.mark.asyncio
    async def test_calls_disconnect_fn(self, mock_exec):
        disconnect_called = []

        async def mock_disconnect():
            disconnect_called.append(True)

        backend = SSHBackendWrapper(
            exec_fn=mock_exec,
            host="test-host.example.com",
            disconnect_fn=mock_disconnect,
        )
        await backend.cleanup()
        assert len(disconnect_called) == 1

    @pytest.mark.asyncio
    async def test_no_disconnect_fn_is_noop(self, backend):
        """cleanup without disconnect_fn should not raise."""
        await backend.cleanup()  # Should not raise


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


class TestInfo:
    """info returns dict with host."""

    def test_contains_host(self, backend):
        info = backend.info()
        assert isinstance(info, dict)
        assert info["host"] == "test-host.example.com"

    def test_contains_env_type(self, backend):
        info = backend.info()
        assert info.get("env_type") == "ssh" or backend.env_type == "ssh"


# ---------------------------------------------------------------------------
# NLSpec: Metadata methods
# ---------------------------------------------------------------------------


class TestMetadata:
    """SSHBackendWrapper must expose working_directory, platform, os_version."""

    def test_working_directory_returns_home(self, backend):
        assert backend.working_directory() == "~"

    def test_platform_returns_string(self, backend):
        result = backend.platform()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_os_version_returns_string(self, backend):
        result = backend.os_version()
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# NLSpec: Timing on exec_command
# ---------------------------------------------------------------------------


class TestExecTiming:
    """exec_command must return duration_ms and timed_out fields."""

    @pytest.mark.asyncio
    async def test_exec_has_duration_ms(self, backend, mock_exec):
        mock_exec.add_response(stdout="ok")
        result = await backend.exec_command("echo ok")
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_exec_has_timed_out_false(self, backend, mock_exec):
        mock_exec.add_response(stdout="ok")
        result = await backend.exec_command("echo ok")
        assert result.timed_out is False


# ---------------------------------------------------------------------------
# NLSpec: env_vars on exec_command
# ---------------------------------------------------------------------------


class TestExecEnvVars:
    """exec_command env_vars should prepend export commands."""

    @pytest.mark.asyncio
    async def test_exec_with_env_vars(self, backend, mock_exec):
        mock_exec.add_response(stdout="ok")
        await backend.exec_command("echo $FOO", env_vars={"FOO": "bar", "BAZ": "qux"})
        cmd = mock_exec.calls[0]["cmd"]
        assert "export FOO=" in cmd
        assert "export BAZ=" in cmd
        # The exports should come before the actual command
        export_pos = cmd.index("export")
        echo_pos = cmd.index("echo")
        assert export_pos < echo_pos

    @pytest.mark.asyncio
    async def test_exec_without_env_vars_unchanged(self, backend, mock_exec):
        mock_exec.add_response(stdout="ok")
        await backend.exec_command("echo hi")
        cmd = mock_exec.calls[0]["cmd"]
        assert cmd == "echo hi"

    @pytest.mark.asyncio
    async def test_exec_env_vars_values_are_quoted(self, backend, mock_exec):
        mock_exec.add_response(stdout="ok")
        await backend.exec_command("echo $X", env_vars={"X": "hello world"})
        cmd = mock_exec.calls[0]["cmd"]
        # Value with spaces must be shell-quoted
        assert "'hello world'" in cmd


# ---------------------------------------------------------------------------
# NLSpec: depth on list_dir
# ---------------------------------------------------------------------------


class TestListDirDepth:
    """list_dir depth parameter controls ls vs find usage."""

    @pytest.mark.asyncio
    async def test_list_dir_depth_1_uses_ls(self, backend, mock_exec):
        mock_exec.add_response(stdout="file.txt\nsubdir/\n")
        await backend.list_dir("/home/user")
        cmd = mock_exec.calls[0]["cmd"]
        assert "ls -1ap" in cmd

    @pytest.mark.asyncio
    async def test_list_dir_depth_2_uses_find(self, backend, mock_exec):
        # Response for find (all entries)
        mock_exec.add_response(stdout="/home/user/a.py\n/home/user/sub\n")
        # Response for find -type d (directories)
        mock_exec.add_response(stdout="/home/user/sub\n")
        await backend.list_dir("/home/user", depth=2)
        cmd = mock_exec.calls[0]["cmd"]
        assert "find" in cmd
        assert "-maxdepth 2" in cmd
        assert "-mindepth 1" in cmd


# ---------------------------------------------------------------------------
# NLSpec: grep params (case_insensitive, max_results)
# ---------------------------------------------------------------------------


class TestGrepParams:
    """grep must support case_insensitive and max_results params."""

    @pytest.mark.asyncio
    async def test_grep_case_insensitive(self, backend, mock_exec):
        mock_exec.add_response(stdout="match\n")
        await backend.grep("pattern", path="/home/user", case_insensitive=True)
        cmd = mock_exec.calls[0]["cmd"]
        assert "-i" in cmd

    @pytest.mark.asyncio
    async def test_grep_max_results(self, backend, mock_exec):
        mock_exec.add_response(stdout="match\n")
        await backend.grep("pattern", path="/home/user", max_results=5)
        cmd = mock_exec.calls[0]["cmd"]
        assert "-m" in cmd
        assert "5" in cmd

    @pytest.mark.asyncio
    async def test_grep_case_insensitive_default_false(self, backend, mock_exec):
        mock_exec.add_response(stdout="match\n")
        await backend.grep("pattern", path="/home/user")
        cmd = mock_exec.calls[0]["cmd"]
        assert "-i" not in cmd

    @pytest.mark.asyncio
    async def test_grep_max_results_default_none(self, backend, mock_exec):
        mock_exec.add_response(stdout="match\n")
        await backend.grep("pattern", path="/home/user")
        cmd = mock_exec.calls[0]["cmd"]
        assert "-m " not in cmd
