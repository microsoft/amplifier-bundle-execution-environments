"""Tests for EnvironmentBackend protocol conformance."""

from __future__ import annotations

from typing import Any

from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.protocol import EnvironmentBackend


# ---------------------------------------------------------------------------
# Test fixtures: a complete and an incomplete backend
# ---------------------------------------------------------------------------


class FakeBackend:
    """Implements every method in the EnvironmentBackend protocol."""

    @property
    def env_type(self) -> str:
        return "fake"

    def working_directory(self) -> str:
        return "/fake"

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
        return EnvExecResult(stdout="", stderr="", exit_code=0)

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        return ""

    async def write_file(self, path: str, content: str) -> None:
        pass

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        return "ok"

    async def file_exists(self, path: str) -> bool:
        return False

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        return []

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        return ""

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        return []

    async def cleanup(self) -> None:
        pass

    def info(self) -> dict[str, Any]:
        return {"type": "fake"}


class IncompleteBackend:
    """Missing most protocol methods — should NOT satisfy the protocol."""

    @property
    def env_type(self) -> str:
        return "incomplete"

    async def exec_command(self, cmd: str) -> EnvExecResult:
        return EnvExecResult(stdout="", stderr="", exit_code=0)

    # Everything else is deliberately absent.


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify runtime-checkable isinstance behaviour."""

    def test_complete_backend_satisfies_protocol(self):
        backend = FakeBackend()
        assert isinstance(backend, EnvironmentBackend)

    def test_incomplete_backend_does_not_satisfy_protocol(self):
        backend = IncompleteBackend()
        assert not isinstance(backend, EnvironmentBackend)

    def test_plain_object_does_not_satisfy_protocol(self):
        assert not isinstance(object(), EnvironmentBackend)


class TestProtocolHasEnvType:
    """env_type property must be part of the protocol."""

    def test_env_type_is_accessible(self):
        backend = FakeBackend()
        assert isinstance(backend, EnvironmentBackend)
        assert backend.env_type == "fake"


class TestProtocolHasCleanupAndInfo:
    """cleanup() and info() are required by the protocol."""

    def test_cleanup_is_required(self):
        """A backend missing cleanup() should not satisfy the protocol."""

        class NoCleanup(FakeBackend):
            cleanup = None  # type: ignore[assignment]

        assert not isinstance(NoCleanup(), EnvironmentBackend)

    def test_info_is_required(self):
        """A backend missing info() should not satisfy the protocol."""

        class NoInfo(FakeBackend):
            info = None  # type: ignore[assignment]

        assert not isinstance(NoInfo(), EnvironmentBackend)


class TestProtocolMetadataMethods:
    """New NLSpec metadata methods: working_directory, platform, os_version."""

    def test_working_directory_is_required(self):
        """A backend missing working_directory() should not satisfy the protocol."""

        class NoWorkingDir(FakeBackend):
            working_directory = None  # type: ignore[assignment]

        assert not isinstance(NoWorkingDir(), EnvironmentBackend)

    def test_platform_is_required(self):
        """A backend missing platform() should not satisfy the protocol."""

        class NoPlatform(FakeBackend):
            platform = None  # type: ignore[assignment]

        assert not isinstance(NoPlatform(), EnvironmentBackend)

    def test_os_version_is_required(self):
        """A backend missing os_version() should not satisfy the protocol."""

        class NoOsVersion(FakeBackend):
            os_version = None  # type: ignore[assignment]

        assert not isinstance(NoOsVersion(), EnvironmentBackend)

    def test_fake_backend_metadata_accessible(self):
        """FakeBackend metadata methods return strings."""
        backend = FakeBackend()
        assert isinstance(backend, EnvironmentBackend)

        wd = backend.working_directory()
        assert isinstance(wd, str)

        plat = backend.platform()
        assert isinstance(plat, str)

        osv = backend.os_version()
        assert isinstance(osv, str)


class TestProtocolIsRuntimeCheckable:
    """The protocol must be decorated with @runtime_checkable."""

    def test_isinstance_does_not_raise(self):
        """isinstance() on a non-runtime-checkable Protocol raises TypeError."""
        # If this doesn't raise, the decorator is present.
        result = isinstance(FakeBackend(), EnvironmentBackend)
        assert result is True
