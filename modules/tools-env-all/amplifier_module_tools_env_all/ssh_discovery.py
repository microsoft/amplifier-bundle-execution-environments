"""SSH credential auto-discovery for env_create.

Discovery chain (tried in order):
1. ~/.ssh/config — parse for matching Host entry
2. Default key paths — try id_ed25519, id_rsa, id_ecdsa
3. Current user — os.getlogin() or $USER
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def discover_ssh_config(host: str) -> dict[str, Any]:
    """Auto-discover SSH connection params for a hostname.

    Parses ~/.ssh/config, checks default key paths, and falls back
    to the current user. Returns a dict of discovered params
    (only non-None values). Explicit params in env_create always
    override these discovered values.
    """
    discovered: dict[str, Any] = {}

    # 1. Parse ~/.ssh/config
    ssh_config = _parse_ssh_config(host)
    if ssh_config:
        if "hostname" in ssh_config:
            discovered["resolved_host"] = ssh_config["hostname"]
        if "user" in ssh_config:
            discovered["username"] = ssh_config["user"]
        if "identityfile" in ssh_config:
            key_path = os.path.expanduser(ssh_config["identityfile"])
            if os.path.exists(key_path):
                discovered["key_file"] = key_path
        if "port" in ssh_config:
            try:
                discovered["port"] = int(ssh_config["port"])
            except ValueError:
                pass

    # 2. Default key paths (if not already found)
    if "key_file" not in discovered:
        for key_name in ("id_ed25519", "id_rsa", "id_ecdsa"):
            key_path = os.path.expanduser(f"~/.ssh/{key_name}")
            if os.path.exists(key_path):
                discovered["key_file"] = key_path
                break

    # 3. Current user (if not already found)
    if "username" not in discovered:
        discovered["username"] = _get_current_user()

    return discovered


def _parse_ssh_config(host: str) -> dict[str, str] | None:
    """Parse ~/.ssh/config for a matching Host entry.

    Returns a dict of lowercase key -> value for the matching host,
    or None if no match found.
    """
    config_path = os.path.expanduser("~/.ssh/config")
    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path) as f:
            lines = f.readlines()
    except (PermissionError, OSError):
        return None

    current_hosts: list[str] = []
    current_config: dict[str, str] = {}
    result: dict[str, str] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Split on first whitespace
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue

        key, value = parts[0].lower(), parts[1].strip()

        if key == "host":
            # Save previous host block if it matched
            if host in current_hosts and current_config:
                result = current_config.copy()
            # Start new host block
            current_hosts = [h.strip() for h in value.split()]
            current_config = {}
        else:
            current_config[key] = value

    # Check last block
    if host in current_hosts and current_config:
        result = current_config.copy()

    return result


def _get_current_user() -> str:
    """Get the current username."""
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USER", os.environ.get("USERNAME", ""))
