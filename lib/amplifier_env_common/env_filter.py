"""Environment variable filtering for execution environments.

Implements the NLSpec Section 4.2 env var policy: filter secrets by default,
keep core system vars, allow explicit overrides.
"""

from __future__ import annotations

from enum import Enum


class EnvVarPolicy(str, Enum):
    """Environment variable inheritance policy."""

    INHERIT_ALL = "inherit_all"
    CORE_ONLY = "core_only"
    INHERIT_NONE = "inherit_none"


# Vars always preserved under core_only policy
CORE_VARS: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "LANG",
        "TERM",
        "TMPDIR",
        "GOPATH",
        "CARGO_HOME",
        "NVM_DIR",
        "PYENV_ROOT",
        "JAVA_HOME",
        "RUSTUP_HOME",
    }
)

# Suffix patterns that indicate secrets (case-insensitive)
SECRET_SUFFIXES: tuple[str, ...] = (
    "_API_KEY",
    "_SECRET",
    "_TOKEN",
    "_PASSWORD",
    "_CREDENTIAL",
    "_AUTH",
)


def _is_secret(name: str) -> bool:
    """Check if a var name matches a known secret pattern (case-insensitive)."""
    upper = name.upper()
    return any(upper.endswith(suffix) for suffix in SECRET_SUFFIXES)


def filter_env_vars(
    policy: EnvVarPolicy,
    base_env: dict[str, str],
    explicit_vars: dict[str, str] | None = None,
) -> dict[str, str]:
    """Apply env var policy to a base environment, then merge explicit overrides.

    Args:
        policy: Which vars to inherit from base_env.
        base_env: The base environment (typically os.environ).
        explicit_vars: Agent-provided env vars that always override.

    Returns:
        Filtered environment dict.
    """
    if policy == EnvVarPolicy.INHERIT_ALL:
        result = dict(base_env)
    elif policy == EnvVarPolicy.CORE_ONLY:
        result = {
            k: v for k, v in base_env.items() if k in CORE_VARS or not _is_secret(k)
        }
    elif policy == EnvVarPolicy.INHERIT_NONE:
        result = {}
    else:
        result = dict(base_env)

    if explicit_vars:
        result.update(explicit_vars)

    return result
