"""Tests for EnvironmentRegistry — instance management."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.registry import EnvironmentRegistry


# ---------------------------------------------------------------------------
# Stub backend that satisfies the EnvironmentBackend protocol
# ---------------------------------------------------------------------------


class FailingCleanupBackend:
    """Backend whose cleanup() always raises."""

    def __init__(self, env_type: str = "local"):
        self._env_type = env_type
        self.cleanup_called = False

    @property
    def env_type(self) -> str:
        return self._env_type

    async def exec_command(
        self, cmd: str, timeout: float | None = None, workdir: str | None = None
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

    async def list_dir(self, path: str) -> list[EnvFileEntry]:
        return []

    async def grep(
        self, pattern: str, path: str | None = None, glob_filter: str | None = None
    ) -> str:
        return ""

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        return []

    async def cleanup(self) -> None:
        self.cleanup_called = True
        raise RuntimeError("cleanup boom")

    def info(self) -> dict[str, Any]:
        return {"type": self._env_type}


class StubBackend:
    """Minimal backend that tracks cleanup calls."""

    def __init__(
        self, env_type: str = "local", info_extra: dict[str, Any] | None = None
    ):
        self._env_type = env_type
        self._info_extra = info_extra or {}
        self.cleaned_up = False

    @property
    def env_type(self) -> str:
        return self._env_type

    async def exec_command(
        self, cmd: str, timeout: float | None = None, workdir: str | None = None
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

    async def list_dir(self, path: str) -> list[EnvFileEntry]:
        return []

    async def grep(
        self, pattern: str, path: str | None = None, glob_filter: str | None = None
    ) -> str:
        return ""

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        return []

    async def cleanup(self) -> None:
        self.cleaned_up = True

    def info(self) -> dict[str, Any]:
        return {"type": self._env_type, **self._info_extra}


# ---------------------------------------------------------------------------
# TestRegistryRegister
# ---------------------------------------------------------------------------


class TestRegistryRegister:
    """Registration and retrieval."""

    def test_register_and_get(self):
        reg = EnvironmentRegistry()
        backend = StubBackend()
        reg.register("dev", backend, env_type="local")
        assert reg.get("dev") is backend

    def test_register_duplicate_name_raises(self):
        reg = EnvironmentRegistry()
        reg.register("dev", StubBackend(), env_type="local")
        with pytest.raises(ValueError, match="already exists"):
            reg.register("dev", StubBackend(), env_type="local")

    def test_get_missing_returns_none(self):
        reg = EnvironmentRegistry()
        assert reg.get("nonexistent") is None

    def test_register_with_metadata(self):
        reg = EnvironmentRegistry()
        reg.register(
            "dev", StubBackend(), env_type="local", metadata={"image": "ubuntu"}
        )
        instances = reg.list_instances()
        assert len(instances) == 1
        assert instances[0]["metadata"] == {"image": "ubuntu"}


# ---------------------------------------------------------------------------
# TestRegistryDestroy
# ---------------------------------------------------------------------------


class TestRegistryDestroy:
    """Destroy and cleanup behaviour."""

    def test_destroy_calls_cleanup(self):
        reg = EnvironmentRegistry()
        backend = StubBackend()
        reg.register("dev", backend, env_type="local")
        asyncio.run(reg.destroy("dev"))
        assert backend.cleaned_up is True
        assert reg.get("dev") is None

    def test_destroy_missing_raises(self):
        reg = EnvironmentRegistry()
        with pytest.raises(KeyError, match="not found"):
            asyncio.run(reg.destroy("ghost"))

    def test_destroy_all(self):
        reg = EnvironmentRegistry()
        backends = [StubBackend() for _ in range(3)]
        for i, b in enumerate(backends):
            reg.register(f"env-{i}", b, env_type="local")
        asyncio.run(reg.destroy_all())
        for b in backends:
            assert b.cleaned_up is True
        assert reg.list_instances() == []

    def test_destroy_all_continues_on_cleanup_failure(self):
        """All backends get cleanup attempted even if one raises."""
        reg = EnvironmentRegistry()
        b1 = StubBackend()
        b2 = FailingCleanupBackend()
        b3 = StubBackend()
        reg.register("b1", b1, env_type="local")
        reg.register("b2", b2, env_type="local")
        reg.register("b3", b3, env_type="local")

        with pytest.raises(RuntimeError, match="cleanup boom"):
            asyncio.run(reg.destroy_all())

        # All three must have had cleanup attempted
        assert b1.cleaned_up is True
        assert b2.cleanup_called is True
        assert b3.cleaned_up is True
        # Registry should be empty after destroy_all
        assert reg.list_instances() == []


# ---------------------------------------------------------------------------
# TestRegistryList
# ---------------------------------------------------------------------------


class TestRegistryList:
    """list_instances output."""

    def test_list_empty(self):
        reg = EnvironmentRegistry()
        assert reg.list_instances() == []

    def test_list_returns_all_instances(self):
        reg = EnvironmentRegistry()
        reg.register("a", StubBackend(env_type="local"), env_type="local")
        reg.register("b", StubBackend(env_type="docker"), env_type="docker")
        result = reg.list_instances()
        names = {r["name"] for r in result}
        types = {r["type"] for r in result}
        assert names == {"a", "b"}
        assert types == {"local", "docker"}

    def test_list_includes_metadata(self):
        reg = EnvironmentRegistry()
        reg.register("dev", StubBackend(), env_type="local", metadata={"gpu": True})
        result = reg.list_instances()
        assert result[0]["metadata"] == {"gpu": True}

    def test_list_includes_backend_info(self):
        reg = EnvironmentRegistry()
        backend = StubBackend(env_type="docker", info_extra={"container_id": "abc123"})
        reg.register("ci", backend, env_type="docker")
        result = reg.list_instances()
        assert result[0]["container_id"] == "abc123"


# ---------------------------------------------------------------------------
# TestRegistryOwned
# ---------------------------------------------------------------------------


class TestRegistryOwned:
    """Tests for owned flag on instances."""

    def test_register_owned_defaults_to_true(self):
        reg = EnvironmentRegistry()
        reg.register("local", StubBackend(), "local")
        instances = reg.list_instances()
        assert instances[0].get("owned") is True

    def test_register_owned_false(self):
        reg = EnvironmentRegistry()
        reg.register("shared", StubBackend(), "docker", owned=False)
        instances = reg.list_instances()
        assert instances[0].get("owned") is False

    @pytest.mark.asyncio
    async def test_destroy_all_skips_unowned(self):
        """destroy_all() only destroys owned instances."""
        reg = EnvironmentRegistry()
        b_owned = StubBackend("docker")
        b_shared = StubBackend("docker")
        reg.register("mine", b_owned, "docker", owned=True)
        reg.register("shared", b_shared, "docker", owned=False)
        await reg.destroy_all()
        assert b_owned.cleaned_up is True
        assert b_shared.cleaned_up is False
        # shared should still be in registry
        assert reg.get("shared") is not None
        # mine should be gone
        assert reg.get("mine") is None

    @pytest.mark.asyncio
    async def test_destroy_explicit_destroys_regardless_of_owned(self):
        """Explicit destroy() works regardless of owned flag."""
        reg = EnvironmentRegistry()
        b = StubBackend("docker")
        reg.register("shared", b, "docker", owned=False)
        await reg.destroy("shared")
        assert b.cleaned_up is True
        assert reg.get("shared") is None

    def test_list_instances_includes_owned(self):
        reg = EnvironmentRegistry()
        reg.register("mine", StubBackend(), "docker", owned=True)
        reg.register("shared", StubBackend(), "docker", owned=False)
        instances = reg.list_instances()
        mine = [i for i in instances if i["name"] == "mine"][0]
        shared = [i for i in instances if i["name"] == "shared"][0]
        assert mine.get("owned") is True
        assert shared.get("owned") is False
