"""EnvironmentRegistry — in-memory mapping from instance names to backends.

Supports register, get, destroy (with cleanup), destroy_all, and list_instances.
Each instance carries a metadata dict slot for decorator config (Phase 4.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import logging

from .protocol import EnvironmentBackend

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentInstance:
    """A registered backend instance with its name and metadata."""

    name: str
    backend: EnvironmentBackend
    env_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    owned: bool = True


class EnvironmentRegistry:
    """In-memory registry mapping instance names to backends."""

    def __init__(self) -> None:
        self._instances: dict[str, EnvironmentInstance] = {}

    def register(
        self,
        name: str,
        backend: EnvironmentBackend,
        env_type: str,
        metadata: dict[str, Any] | None = None,
        owned: bool = True,
    ) -> None:
        """Register a backend instance. Raises ValueError on duplicate name."""
        if name in self._instances:
            raise ValueError(f"Instance '{name}' already exists")
        self._instances[name] = EnvironmentInstance(
            name=name,
            backend=backend,
            env_type=env_type,
            metadata=metadata or {},
            owned=owned,
        )

    def get(self, name: str) -> EnvironmentBackend | None:
        """Get a backend by instance name, or None if not found."""
        instance = self._instances.get(name)
        return instance.backend if instance is not None else None

    async def destroy(self, name: str) -> None:
        """Destroy an instance: call backend.cleanup() and remove from registry.

        Raises KeyError if the instance is not found.
        """
        # Pop first: ensures a failed cleanup() doesn't leave a broken
        # instance in the registry that blocks future operations.
        instance = self._instances.pop(name, None)
        if instance is None:
            raise KeyError(f"Instance '{name}' not found")
        await instance.backend.cleanup()

    async def destroy_all(self) -> None:
        """Destroy all owned instances. Unowned instances are kept.

        Continues past individual failures.
        """
        names = [name for name, inst in self._instances.items() if inst.owned]
        first_error: Exception | None = None
        for name in names:
            try:
                await self.destroy(name)
            except Exception as exc:
                logger.warning("registry: cleanup failed for '%s': %s", name, exc)
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    def list_instances(self) -> list[dict[str, Any]]:
        """Return a list of dicts describing all registered instances.

        Each dict contains name, type, metadata, and merged backend.info() fields.
        """
        result = []
        for instance in self._instances.values():
            entry: dict[str, Any] = {
                **instance.backend.info(),
                "name": instance.name,
                "type": instance.env_type,
                "metadata": instance.metadata,
                "owned": instance.owned,
            }
            result.append(entry)
        return result
