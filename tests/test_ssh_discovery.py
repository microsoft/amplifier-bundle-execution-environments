"""Tests for SSH credential auto-discovery.

Tests the discovery chain:
1. ~/.ssh/config parsing
2. Default key path fallback
3. Current user fallback
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Tests for _parse_ssh_config()
# ---------------------------------------------------------------------------


class TestParseSSHConfig:
    """Low-level ~/.ssh/config parser tests."""

    def test_parse_ssh_config_finds_host(self, tmp_path: Path) -> None:
        """Matching Host entry is found and returned."""
        config = tmp_path / "config"
        config.write_text(
            textwrap.dedent("""\
                Host myserver
                    HostName 192.168.1.10
                    User admin
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import _parse_ssh_config

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
            return_value=str(config),
        ):
            result = _parse_ssh_config("myserver")

        assert result is not None
        assert result["hostname"] == "192.168.1.10"
        assert result["user"] == "admin"

    def test_parse_ssh_config_no_match(self, tmp_path: Path) -> None:
        """Host not in config returns None."""
        config = tmp_path / "config"
        config.write_text(
            textwrap.dedent("""\
                Host otherbox
                    HostName 10.0.0.1
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import _parse_ssh_config

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
            return_value=str(config),
        ):
            result = _parse_ssh_config("myserver")

        assert result is None

    def test_parse_ssh_config_extracts_all_fields(self, tmp_path: Path) -> None:
        """User, HostName, IdentityFile, Port all extracted."""
        config = tmp_path / "config"
        config.write_text(
            textwrap.dedent("""\
                Host devbox
                    HostName dev.example.com
                    User deploy
                    IdentityFile ~/.ssh/id_deploy
                    Port 2222
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import _parse_ssh_config

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
            return_value=str(config),
        ):
            result = _parse_ssh_config("devbox")

        assert result is not None
        assert result["hostname"] == "dev.example.com"
        assert result["user"] == "deploy"
        assert result["identityfile"] == "~/.ssh/id_deploy"
        assert result["port"] == "2222"

    def test_parse_ssh_config_multiple_hosts(self, tmp_path: Path) -> None:
        """Parser finds the correct host among multiple entries."""
        config = tmp_path / "config"
        config.write_text(
            textwrap.dedent("""\
                Host alpha
                    HostName alpha.example.com
                    User alice

                Host beta
                    HostName beta.example.com
                    User bob
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import _parse_ssh_config

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
            return_value=str(config),
        ):
            result = _parse_ssh_config("beta")

        assert result is not None
        assert result["hostname"] == "beta.example.com"
        assert result["user"] == "bob"

    def test_parse_ssh_config_comments_and_blanks(self, tmp_path: Path) -> None:
        """Comments and blank lines are ignored."""
        config = tmp_path / "config"
        config.write_text(
            textwrap.dedent("""\
                # Global settings

                Host myhost
                    # This is the main server
                    HostName 10.0.0.5
                    User root
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import _parse_ssh_config

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
            return_value=str(config),
        ):
            result = _parse_ssh_config("myhost")

        assert result is not None
        assert result["hostname"] == "10.0.0.5"
        assert result["user"] == "root"


# ---------------------------------------------------------------------------
# Tests for discover_ssh_config() — full discovery chain
# ---------------------------------------------------------------------------


class TestDiscoverSSHConfig:
    """Full discovery chain: ssh config → default keys → current user."""

    def test_discover_finds_key_from_config(self, tmp_path: Path) -> None:
        """When ssh config has IdentityFile and the file exists, it's used."""
        config = tmp_path / "config"
        key_file = tmp_path / "id_custom"
        key_file.write_text("fake-key")

        config.write_text(
            textwrap.dedent(f"""\
                Host myserver
                    HostName 10.0.0.1
                    User admin
                    IdentityFile {key_file}
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        def fake_expanduser(path: str) -> str:
            if path == "~/.ssh/config":
                return str(config)
            return path  # IdentityFile path is already absolute in this test

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
            side_effect=fake_expanduser,
        ):
            result = discover_ssh_config("myserver")

        assert result["key_file"] == str(key_file)
        assert result["username"] == "admin"
        assert result["resolved_host"] == "10.0.0.1"

    def test_discover_falls_back_to_default_keys(self, tmp_path: Path) -> None:
        """When no ssh config match, tries default key paths."""
        # Create a fake id_ed25519 key
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        ed25519_key = ssh_dir / "id_ed25519"
        ed25519_key.write_text("fake-key")

        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        def fake_expanduser(path: str) -> str:
            if path == "~/.ssh/config":
                return str(tmp_path / ".ssh" / "config")  # Doesn't exist
            if path.startswith("~/.ssh/"):
                return str(tmp_path / ".ssh" / path.split("/")[-1])
            return path

        with (
            patch(
                "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
                side_effect=fake_expanduser,
            ),
            patch(
                "amplifier_module_tools_env_all.ssh_discovery._get_current_user",
                return_value="testuser",
            ),
        ):
            result = discover_ssh_config("somehost")

        assert result["key_file"] == str(ed25519_key)

    def test_discover_prefers_ed25519_over_rsa(self, tmp_path: Path) -> None:
        """Default key priority: id_ed25519 > id_rsa > id_ecdsa."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_ed25519").write_text("ed25519-key")
        (ssh_dir / "id_rsa").write_text("rsa-key")

        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        def fake_expanduser(path: str) -> str:
            if path == "~/.ssh/config":
                return str(tmp_path / ".ssh" / "config")  # Doesn't exist
            if path.startswith("~/.ssh/"):
                return str(tmp_path / ".ssh" / path.split("/")[-1])
            return path

        with (
            patch(
                "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
                side_effect=fake_expanduser,
            ),
            patch(
                "amplifier_module_tools_env_all.ssh_discovery._get_current_user",
                return_value="testuser",
            ),
        ):
            result = discover_ssh_config("somehost")

        assert result["key_file"] == str(ssh_dir / "id_ed25519")

    def test_discover_falls_back_to_current_user(self, tmp_path: Path) -> None:
        """When no User in config, uses _get_current_user()."""
        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        def fake_expanduser(path: str) -> str:
            if path == "~/.ssh/config":
                return str(tmp_path / "nonexistent_config")
            if path.startswith("~/.ssh/"):
                return str(tmp_path / path.split("/")[-1])  # No keys exist
            return path

        with (
            patch(
                "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
                side_effect=fake_expanduser,
            ),
            patch(
                "amplifier_module_tools_env_all.ssh_discovery._get_current_user",
                return_value="janedoe",
            ),
        ):
            result = discover_ssh_config("unknownhost")

        assert result["username"] == "janedoe"

    def test_missing_ssh_config_no_error(self, tmp_path: Path) -> None:
        """If ~/.ssh/config doesn't exist, returns defaults gracefully."""
        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        def fake_expanduser(path: str) -> str:
            # Point everything to tmp_path where nothing exists
            if path == "~/.ssh/config":
                return str(tmp_path / "no_such_config")
            if path.startswith("~/.ssh/"):
                return str(tmp_path / path.split("/")[-1])
            return path

        with (
            patch(
                "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
                side_effect=fake_expanduser,
            ),
            patch(
                "amplifier_module_tools_env_all.ssh_discovery._get_current_user",
                return_value="fallback",
            ),
        ):
            result = discover_ssh_config("anyhost")

        # Should have username from fallback, no key_file, no resolved_host
        assert result["username"] == "fallback"
        assert "key_file" not in result
        assert "resolved_host" not in result

    def test_discover_port_from_config(self, tmp_path: Path) -> None:
        """Port from ssh config is parsed as int."""
        config = tmp_path / "config"
        config.write_text(
            textwrap.dedent("""\
                Host myserver
                    Port 2222
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        def fake_expanduser(path: str) -> str:
            if path == "~/.ssh/config":
                return str(config)
            if path.startswith("~/.ssh/"):
                return str(tmp_path / path.split("/")[-1])
            return path

        with (
            patch(
                "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
                side_effect=fake_expanduser,
            ),
            patch(
                "amplifier_module_tools_env_all.ssh_discovery._get_current_user",
                return_value="testuser",
            ),
        ):
            result = discover_ssh_config("myserver")

        assert result["port"] == 2222

    def test_explicit_params_not_overridden(self, tmp_path: Path) -> None:
        """discover returns discovered values; caller merges (discovery doesn't know about explicit params)."""
        config = tmp_path / "config"
        config.write_text(
            textwrap.dedent("""\
                Host myserver
                    User discovered_user
                    HostName 10.0.0.1
            """)
        )

        from amplifier_module_tools_env_all.ssh_discovery import discover_ssh_config

        with patch(
            "amplifier_module_tools_env_all.ssh_discovery.os.path.expanduser",
            return_value=str(config),
        ):
            result = discover_ssh_config("myserver")

        # discover_ssh_config returns what it found — it's the caller's job to merge
        assert result["username"] == "discovered_user"
        assert result["resolved_host"] == "10.0.0.1"

        # Simulate caller merge: explicit wins
        explicit_username = "explicit_user"
        final_username = explicit_username or result.get("username")
        assert final_username == "explicit_user"
