"""Tests for env-common shared models."""

import pytest

from amplifier_env_common.models import (
    EnvError,
    EnvExecResult,
    EnvFileEntry,
)


class TestEnvError:
    """Tests for the common error structure."""

    def test_operation_error(self):
        err = EnvError(
            error_type="operation",
            error_code="file_not_found",
            message="File /tmp/missing.txt not found",
            retriable=False,
            environment="local",
        )
        assert err.error_type == "operation"
        assert err.error_code == "file_not_found"
        assert err.retriable is False
        assert err.environment == "local"

    def test_transport_error(self):
        err = EnvError(
            error_type="transport",
            error_code="connection_lost",
            message="SSH connection dropped",
            retriable=True,
            environment="ssh",
        )
        assert err.error_type == "transport"
        assert err.retriable is True

    def test_error_type_validation(self):
        """error_type must be 'transport' or 'operation'."""
        with pytest.raises(ValueError):
            EnvError(
                error_type="invalid",
                error_code="test",
                message="test",
                retriable=False,
                environment="local",
            )

    def test_to_tool_error(self):
        err = EnvError(
            error_type="operation",
            error_code="file_not_found",
            message="Not found",
            retriable=False,
            environment="docker",
        )
        d = err.to_tool_error()
        assert d == {
            "error_type": "operation",
            "error_code": "file_not_found",
            "message": "Not found",
            "retriable": False,
            "environment": "docker",
        }


class TestEnvExecResult:
    """Tests for exec command result."""

    def test_success(self):
        result = EnvExecResult(stdout="hello\n", stderr="", exit_code=0)
        assert result.exit_code == 0
        assert result.stdout == "hello\n"

    def test_failure(self):
        result = EnvExecResult(stdout="", stderr="not found", exit_code=1)
        assert result.exit_code == 1
        assert result.stderr == "not found"

    def test_timed_out_defaults_to_false(self):
        result = EnvExecResult(stdout="", stderr="", exit_code=0)
        assert result.timed_out is False

    def test_duration_ms_defaults_to_zero(self):
        result = EnvExecResult(stdout="", stderr="", exit_code=0)
        assert result.duration_ms == 0

    def test_timed_out_can_be_set(self):
        result = EnvExecResult(stdout="", stderr="", exit_code=137, timed_out=True)
        assert result.timed_out is True

    def test_duration_ms_can_be_set(self):
        result = EnvExecResult(stdout="ok", stderr="", exit_code=0, duration_ms=1500)
        assert result.duration_ms == 1500

    def test_existing_construction_still_works(self):
        """Backward compat: constructing with only original fields works."""
        result = EnvExecResult(stdout="hi", stderr="", exit_code=0)
        assert result.stdout == "hi"
        assert result.stderr == ""
        assert result.exit_code == 0


class TestEnvFileEntry:
    """Tests for directory listing entries."""

    def test_file_entry(self):
        entry = EnvFileEntry(name="main.py", entry_type="file", size=1024)
        assert entry.name == "main.py"
        assert entry.entry_type == "file"

    def test_dir_entry(self):
        entry = EnvFileEntry(name="src", entry_type="dir")
        assert entry.entry_type == "dir"
        assert entry.size is None
