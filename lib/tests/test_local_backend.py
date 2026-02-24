"""Tests for LocalBackend — host filesystem execution environment."""

from __future__ import annotations

import os

import pytest

from amplifier_env_common.backends.local import LocalBackend
from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.protocol import EnvironmentBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def backend(tmp_path):
    """Create a LocalBackend scoped to a temporary directory."""
    return LocalBackend(working_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """LocalBackend must satisfy the EnvironmentBackend protocol."""

    def test_isinstance_check(self, backend):
        assert isinstance(backend, EnvironmentBackend)

    def test_env_type_is_local(self, backend):
        assert backend.env_type == "local"


# ---------------------------------------------------------------------------
# Metadata methods
# ---------------------------------------------------------------------------


class TestMetadata:
    """Metadata methods: working_directory, platform, os_version."""

    def test_working_directory(self, backend, tmp_path):
        assert backend.working_directory() == str(tmp_path)

    def test_platform_returns_string(self, backend):
        result = backend.platform()
        assert result in ("linux", "darwin", "windows") or isinstance(result, str)

    def test_os_version_returns_string(self, backend):
        result = backend.os_version()
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------


class TestPathTraversal:
    """_resolve must reject paths that escape the working directory."""

    @pytest.mark.asyncio
    async def test_traversal_read_blocked(self, backend):
        with pytest.raises(ValueError, match="escapes working directory"):
            await backend.read_file("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_traversal_write_blocked(self, backend):
        with pytest.raises(ValueError, match="escapes working directory"):
            await backend.write_file("../../tmp/evil.txt", "x")

    @pytest.mark.asyncio
    async def test_traversal_edit_blocked(self, backend):
        with pytest.raises(ValueError, match="escapes working directory"):
            await backend.edit_file("../../etc/hosts", "x", "y")


# ---------------------------------------------------------------------------
# exec_command
# ---------------------------------------------------------------------------


class TestExecCommand:
    """exec_command wraps asyncio.create_subprocess_shell."""

    @pytest.mark.asyncio
    async def test_echo_returns_stdout(self, backend):
        result = await backend.exec_command("echo hello")
        assert isinstance(result, EnvExecResult)
        assert result.stdout.strip() == "hello"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, backend):
        result = await backend.exec_command("exit 42")
        assert result.exit_code == 42

    @pytest.mark.asyncio
    async def test_stderr_captured(self, backend):
        result = await backend.exec_command("echo oops >&2")
        assert "oops" in result.stderr

    @pytest.mark.asyncio
    async def test_workdir_honored(self, backend, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        result = await backend.exec_command("pwd", workdir=str(subdir))
        assert result.stdout.strip() == str(subdir)

    @pytest.mark.asyncio
    async def test_exec_has_duration_ms(self, backend):
        result = await backend.exec_command("sleep 0.05")
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_exec_timeout_returns_timed_out(self, backend):
        result = await backend.exec_command("sleep 10", timeout=0.1)
        assert result.timed_out is True
        assert result.exit_code == -1
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_exec_with_env_vars(self, backend):
        result = await backend.exec_command(
            "echo $MY_VAR", env_vars={"MY_VAR": "hello"}
        )
        assert result.stdout.strip() == "hello"


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    """read_file reads from the host filesystem."""

    @pytest.mark.asyncio
    async def test_reads_content(self, backend, tmp_path):
        (tmp_path / "hello.txt").write_text("hello world\n")
        content = await backend.read_file("hello.txt")
        assert content == "hello world\n"

    @pytest.mark.asyncio
    async def test_offset_and_limit(self, backend, tmp_path):
        (tmp_path / "lines.txt").write_text("line1\nline2\nline3\nline4\n")
        # offset=2 means start at line 2 (1-indexed), limit=2 means 2 lines
        content = await backend.read_file("lines.txt", offset=2, limit=2)
        assert content == "line2\nline3\n"

    @pytest.mark.asyncio
    async def test_offset_only(self, backend, tmp_path):
        (tmp_path / "lines.txt").write_text("line1\nline2\nline3\n")
        content = await backend.read_file("lines.txt", offset=2)
        assert content == "line2\nline3\n"

    @pytest.mark.asyncio
    async def test_limit_only(self, backend, tmp_path):
        (tmp_path / "lines.txt").write_text("line1\nline2\nline3\n")
        content = await backend.read_file("lines.txt", limit=1)
        assert content == "line1\n"

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, backend):
        with pytest.raises(FileNotFoundError):
            await backend.read_file("does_not_exist.txt")


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


class TestWriteFile:
    """write_file creates files and parent directories."""

    @pytest.mark.asyncio
    async def test_creates_file(self, backend, tmp_path):
        await backend.write_file("new.txt", "content")
        assert (tmp_path / "new.txt").read_text() == "content"

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, backend, tmp_path):
        await backend.write_file("a/b/c/deep.txt", "deep content")
        assert (tmp_path / "a" / "b" / "c" / "deep.txt").read_text() == "deep content"


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------


class TestEditFile:
    """edit_file replaces a unique string in-place."""

    @pytest.mark.asyncio
    async def test_replaces_unique_string(self, backend, tmp_path):
        (tmp_path / "edit.txt").write_text("hello world")
        result = await backend.edit_file("edit.txt", "hello", "goodbye")
        assert "1 occurrence" in result or "Edited" in result
        assert (tmp_path / "edit.txt").read_text() == "goodbye world"

    @pytest.mark.asyncio
    async def test_string_not_found_raises(self, backend, tmp_path):
        (tmp_path / "edit.txt").write_text("hello world")
        with pytest.raises(ValueError, match="not found"):
            await backend.edit_file("edit.txt", "nonexistent", "replacement")

    @pytest.mark.asyncio
    async def test_string_not_unique_raises(self, backend, tmp_path):
        (tmp_path / "edit.txt").write_text("aaa bbb aaa")
        with pytest.raises(ValueError, match="not unique"):
            await backend.edit_file("edit.txt", "aaa", "ccc")

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, backend):
        with pytest.raises(FileNotFoundError):
            await backend.edit_file("nope.txt", "a", "b")


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExists:
    """file_exists checks the host filesystem."""

    @pytest.mark.asyncio
    async def test_existing_file(self, backend, tmp_path):
        (tmp_path / "exists.txt").write_text("hi")
        assert await backend.file_exists("exists.txt") is True

    @pytest.mark.asyncio
    async def test_missing_file(self, backend):
        assert await backend.file_exists("nope.txt") is False

    @pytest.mark.asyncio
    async def test_existing_directory(self, backend, tmp_path):
        (tmp_path / "mydir").mkdir()
        assert await backend.file_exists("mydir") is True


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


class TestListDir:
    """list_dir returns structured EnvFileEntry list."""

    @pytest.mark.asyncio
    async def test_returns_entries(self, backend, tmp_path):
        (tmp_path / "file.txt").write_text("content")
        (tmp_path / "subdir").mkdir()
        entries = await backend.list_dir(".")
        assert isinstance(entries, list)
        assert all(isinstance(e, EnvFileEntry) for e in entries)
        names = {e.name for e in entries}
        assert "file.txt" in names
        assert "subdir" in names

    @pytest.mark.asyncio
    async def test_entry_types(self, backend, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "d").mkdir()
        entries = await backend.list_dir(".")
        by_name = {e.name: e for e in entries}
        assert by_name["a.txt"].entry_type == "file"
        assert by_name["d"].entry_type == "dir"

    @pytest.mark.asyncio
    async def test_file_has_size(self, backend, tmp_path):
        (tmp_path / "sized.txt").write_text("12345")
        entries = await backend.list_dir(".")
        by_name = {e.name: e for e in entries}
        assert by_name["sized.txt"].size == 5

    @pytest.mark.asyncio
    async def test_dir_has_no_size(self, backend, tmp_path):
        (tmp_path / "d").mkdir()
        entries = await backend.list_dir(".")
        by_name = {e.name: e for e in entries}
        assert by_name["d"].size is None

    @pytest.mark.asyncio
    async def test_list_dir_depth_1(self, backend, tmp_path):
        """Default depth=1 only lists immediate children (no nested entries)."""
        sub = tmp_path / "parent"
        sub.mkdir()
        (sub / "child").mkdir()
        (tmp_path / "top.txt").write_text("x")
        entries = await backend.list_dir(".")
        names = {e.name for e in entries}
        assert "parent" in names
        assert "top.txt" in names
        # child should NOT appear at depth=1
        assert "child" not in names
        assert "parent/child" not in names

    @pytest.mark.asyncio
    async def test_list_dir_depth_2(self, backend, tmp_path):
        """depth=2 shows nested entries with relative paths."""
        sub = tmp_path / "parent"
        sub.mkdir()
        (sub / "child.txt").write_text("x")
        (sub / "nested_dir").mkdir()
        entries = await backend.list_dir(".", depth=2)
        names = {e.name for e in entries}
        assert "parent" in names
        assert "parent/child.txt" in names
        assert "parent/nested_dir" in names

    @pytest.mark.asyncio
    async def test_missing_dir_raises(self, backend):
        with pytest.raises(FileNotFoundError):
            await backend.list_dir("nonexistent")

    @pytest.mark.asyncio
    async def test_sorted_by_name(self, backend, tmp_path):
        for name in ["c.txt", "a.txt", "b.txt"]:
            (tmp_path / name).write_text("x")
        entries = await backend.list_dir(".")
        names = [e.name for e in entries]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


class TestGrep:
    """grep searches file contents."""

    @pytest.mark.asyncio
    async def test_finds_match(self, backend, tmp_path):
        (tmp_path / "haystack.txt").write_text("needle in a haystack\n")
        result = await backend.grep("needle")
        assert "needle" in result

    @pytest.mark.asyncio
    async def test_no_match_returns_no_matches(self, backend, tmp_path):
        (tmp_path / "empty.txt").write_text("nothing here\n")
        result = await backend.grep("zzzzz_nonexistent_zzzzz")
        assert "No matches" in result or result.strip() == ""

    @pytest.mark.asyncio
    async def test_grep_case_insensitive(self, backend, tmp_path):
        (tmp_path / "mixed.txt").write_text("Hello World\n")
        result = await backend.grep("hello", case_insensitive=True)
        assert "Hello" in result

    @pytest.mark.asyncio
    async def test_grep_case_sensitive_default(self, backend, tmp_path):
        (tmp_path / "mixed.txt").write_text("Hello World\n")
        result = await backend.grep("hello")
        assert "No matches" in result or result.strip() == ""

    @pytest.mark.asyncio
    async def test_grep_max_results(self, backend, tmp_path):
        (tmp_path / "multi.txt").write_text("match1\nmatch2\nmatch3\n")
        result = await backend.grep("match", max_results=1)
        lines = [line for line in result.strip().splitlines() if line.strip()]
        assert len(lines) == 1

    @pytest.mark.asyncio
    async def test_bad_pattern_raises(self, backend, tmp_path):
        """grep exit code > 1 (bad regex) must raise RuntimeError."""
        (tmp_path / "file.txt").write_text("content\n")
        with pytest.raises(RuntimeError, match="grep failed"):
            await backend.grep("[invalid")  # unclosed bracket = bad regex


# ---------------------------------------------------------------------------
# glob_files
# ---------------------------------------------------------------------------


class TestGlobFiles:
    """glob_files finds files matching patterns."""

    @pytest.mark.asyncio
    async def test_finds_py_files(self, backend, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        matches = await backend.glob_files("*.py")
        assert sorted(matches) == ["a.py", "b.py"]

    @pytest.mark.asyncio
    async def test_recursive_glob(self, backend, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("")
        (tmp_path / "top.py").write_text("")
        matches = await backend.glob_files("**/*.py")
        assert "top.py" in matches
        assert any("deep.py" in m for m in matches)

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, backend):
        matches = await backend.glob_files("*.nonexistent")
        assert matches == []


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    """cleanup is a no-op for local backend."""

    @pytest.mark.asyncio
    async def test_cleanup_does_not_raise(self, backend):
        await backend.cleanup()  # Should not raise


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


class TestInfo:
    """info returns metadata about the backend."""

    def test_contains_working_dir(self, backend, tmp_path):
        info = backend.info()
        assert isinstance(info, dict)
        assert "working_dir" in info
        assert info["working_dir"] == str(tmp_path)


# ---------------------------------------------------------------------------
# Phase 4.3 B.1+B.2: NLSpec process group management
# ---------------------------------------------------------------------------


class TestExecProcessGroup:
    """Tests for NLSpec process group management (Section 4.2).

    Verifies: new session group, SIGTERM→wait→SIGKILL graceful shutdown,
    child process cleanup via process group kill.
    """

    @pytest.mark.asyncio
    async def test_subprocess_uses_new_session(self, tmp_path):
        """Verify subprocess is spawned in a new process group."""
        import os

        backend = LocalBackend(working_dir=str(tmp_path), env_policy="inherit_all")
        # Report the process group ID of the subprocess vs our own
        result = await backend.exec_command("echo $PPID; ps -o pgid= -p $$")
        assert result.exit_code == 0
        # The subprocess pgid should differ from our pgid
        our_pgid = os.getpgrp()
        lines = result.stdout.strip().split("\n")
        child_pgid = int(lines[-1].strip())
        assert child_pgid != our_pgid, (
            f"Child pgid {child_pgid} should differ from parent pgid {our_pgid}"
        )

    @pytest.mark.asyncio
    async def test_timeout_returns_timed_out_result(self, tmp_path):
        """Timeout should return EnvExecResult with timed_out=True, not raise."""
        backend = LocalBackend(working_dir=str(tmp_path), env_policy="inherit_all")
        result = await backend.exec_command("sleep 60", timeout=0.5)
        assert result.timed_out is True
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_timeout_kills_child_processes(self, tmp_path):
        """Child processes spawned by the command should also be killed."""
        import asyncio
        import subprocess

        backend = LocalBackend(working_dir=str(tmp_path), env_policy="inherit_all")
        # Spawn a command that creates a child process writing a marker
        # Use a unique marker so we don't collide with other tests
        marker = f"sleep_pg_test_{os.getpid()}"
        result = await backend.exec_command(
            f"bash -c '{marker}=1; sleep 300 & echo $!; wait'",
            timeout=0.5,
        )
        assert result.timed_out is True
        # Give a moment for cleanup
        await asyncio.sleep(0.5)
        # Check that no sleep 300 processes from our child are lingering
        check = subprocess.run(
            ["pgrep", "-f", "sleep 300"],
            capture_output=True,
            text=True,
        )
        assert check.returncode != 0, "sleep 300 process should have been killed"


# ---------------------------------------------------------------------------
# Phase 4.3 A.3: env var filtering in exec_command
# ---------------------------------------------------------------------------


class TestExecEnvFiltering:
    """exec_command applies env var filtering based on env_policy."""

    @pytest.mark.asyncio
    async def test_exec_filters_secrets_by_default(self, tmp_path, monkeypatch):
        """Default core_only policy filters env vars matching secret patterns."""
        monkeypatch.setenv("FAKE_API_KEY", "supersecret")
        backend = LocalBackend(working_dir=str(tmp_path))
        result = await backend.exec_command("echo $FAKE_API_KEY")
        # core_only filters vars ending in _API_KEY
        assert result.stdout.strip() == ""

    @pytest.mark.asyncio
    async def test_exec_inherit_all_passes_secrets(self, tmp_path, monkeypatch):
        """inherit_all policy passes all env vars including secrets."""
        monkeypatch.setenv("FAKE_API_KEY", "supersecret")
        backend = LocalBackend(working_dir=str(tmp_path), env_policy="inherit_all")
        result = await backend.exec_command("echo $FAKE_API_KEY")
        assert result.stdout.strip() == "supersecret"

    @pytest.mark.asyncio
    async def test_exec_inherit_none_blocks_everything(self, tmp_path, monkeypatch):
        """inherit_none policy blocks all host env vars."""
        monkeypatch.setenv("CUSTOM_TEST_VAR", "should_vanish")
        backend = LocalBackend(working_dir=str(tmp_path), env_policy="inherit_none")
        result = await backend.exec_command("echo $CUSTOM_TEST_VAR")
        # CUSTOM_TEST_VAR should not be visible under inherit_none
        assert result.stdout.strip() == ""

    @pytest.mark.asyncio
    async def test_exec_explicit_env_vars_override_filter(self, tmp_path):
        """Explicit env_vars always visible, even with core_only filtering."""
        backend = LocalBackend(working_dir=str(tmp_path))
        result = await backend.exec_command(
            "echo $OPENAI_API_KEY", env_vars={"OPENAI_API_KEY": "sk-test"}
        )
        assert result.stdout.strip() == "sk-test"

    @pytest.mark.asyncio
    async def test_exec_core_only_keeps_path(self, tmp_path):
        """core_only policy preserves core vars like PATH."""
        backend = LocalBackend(working_dir=str(tmp_path))
        result = await backend.exec_command("echo $PATH")
        # PATH should still be present under core_only
        assert result.stdout.strip() != ""
