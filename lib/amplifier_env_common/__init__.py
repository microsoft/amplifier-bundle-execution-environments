"""Shared models and schemas for the execution environment ecosystem.

This package defines the contract types used across all env-* bundles:
- protocol: EnvironmentBackend — the uniform interface for all backends
- models: EnvError, EnvExecResult, EnvFileEntry
- schemas: JSON schemas for the 8 common-shape tools
"""

from .env_filter import EnvVarPolicy, filter_env_vars
from .models import EnvError, EnvExecResult, EnvFileEntry
from .protocol import EnvironmentBackend
from .registry import EnvironmentInstance, EnvironmentRegistry
from .schemas import (
    ENV_EDIT_FILE_SCHEMA,
    ENV_EXEC_SCHEMA,
    ENV_FILE_EXISTS_SCHEMA,
    ENV_GLOB_SCHEMA,
    ENV_GREP_SCHEMA,
    ENV_LIST_DIR_SCHEMA,
    ENV_READ_FILE_SCHEMA,
    ENV_WRITE_FILE_SCHEMA,
)

__all__ = [
    "EnvVarPolicy",
    "filter_env_vars",
    "EnvironmentBackend",
    "EnvironmentInstance",
    "EnvironmentRegistry",
    "EnvError",
    "EnvExecResult",
    "EnvFileEntry",
    "ENV_EDIT_FILE_SCHEMA",
    "ENV_EXEC_SCHEMA",
    "ENV_FILE_EXISTS_SCHEMA",
    "ENV_GLOB_SCHEMA",
    "ENV_GREP_SCHEMA",
    "ENV_LIST_DIR_SCHEMA",
    "ENV_READ_FILE_SCHEMA",
    "ENV_WRITE_FILE_SCHEMA",
]
