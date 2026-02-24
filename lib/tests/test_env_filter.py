"""Tests for env variable filtering."""

from __future__ import annotations


from amplifier_env_common.env_filter import EnvVarPolicy, filter_env_vars


class TestEnvVarPolicyEnum:
    def test_inherit_all_value(self):
        assert EnvVarPolicy.INHERIT_ALL == "inherit_all"

    def test_core_only_value(self):
        assert EnvVarPolicy.CORE_ONLY == "core_only"

    def test_inherit_none_value(self):
        assert EnvVarPolicy.INHERIT_NONE == "inherit_none"


class TestFilterInheritAll:
    def test_passes_everything_through(self):
        base = {"PATH": "/usr/bin", "SECRET_API_KEY": "sk-123", "CUSTOM": "val"}
        result = filter_env_vars(EnvVarPolicy.INHERIT_ALL, base)
        assert result == base

    def test_explicit_vars_override(self):
        base = {"PATH": "/usr/bin", "MY_VAR": "old"}
        result = filter_env_vars(EnvVarPolicy.INHERIT_ALL, base, {"MY_VAR": "new"})
        assert result["MY_VAR"] == "new"


class TestFilterCoreOnly:
    def test_keeps_core_vars(self):
        base = {"PATH": "/usr/bin", "HOME": "/home/user", "USER": "dev"}
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "PATH" in result
        assert "HOME" in result
        assert "USER" in result

    def test_filters_api_keys(self):
        base = {
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "sk-123",
            "ANTHROPIC_API_KEY": "sk-456",
        }
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "OPENAI_API_KEY" not in result
        assert "ANTHROPIC_API_KEY" not in result
        assert "PATH" in result

    def test_filters_secrets(self):
        base = {
            "PATH": "/usr/bin",
            "DB_PASSWORD": "pass",
            "AWS_SECRET": "sec",
            "AUTH_TOKEN": "tok",
        }
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "DB_PASSWORD" not in result
        assert "AWS_SECRET" not in result
        assert "AUTH_TOKEN" not in result

    def test_filters_credential(self):
        base = {"PATH": "/usr/bin", "AZURE_CREDENTIAL": "cred"}
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "AZURE_CREDENTIAL" not in result

    def test_filters_auth(self):
        base = {"PATH": "/usr/bin", "GH_AUTH": "ghp_xxx"}
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "GH_AUTH" not in result

    def test_case_insensitive_filtering(self):
        base = {"PATH": "/usr/bin", "my_api_key": "val", "Some_Secret": "val"}
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "my_api_key" not in result
        assert "Some_Secret" not in result

    def test_keeps_language_paths(self):
        base = {
            "GOPATH": "/go",
            "CARGO_HOME": "/cargo",
            "NVM_DIR": "/nvm",
            "JAVA_HOME": "/java",
        }
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "GOPATH" in result
        assert "CARGO_HOME" in result
        assert "NVM_DIR" in result
        assert "JAVA_HOME" in result

    def test_keeps_non_secret_vars(self):
        base = {
            "PATH": "/usr/bin",
            "EDITOR": "vim",
            "DISPLAY": ":0",
            "MY_APP_PORT": "8080",
        }
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, base)
        assert "EDITOR" in result
        assert "DISPLAY" in result
        assert "MY_APP_PORT" in result

    def test_explicit_vars_override_filter(self):
        """Agent can explicitly pass a secret if needed."""
        base = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-filtered"}
        result = filter_env_vars(
            EnvVarPolicy.CORE_ONLY, base, {"OPENAI_API_KEY": "sk-explicit"}
        )
        assert result["OPENAI_API_KEY"] == "sk-explicit"


class TestFilterInheritNone:
    def test_empty_without_explicit(self):
        base = {"PATH": "/usr/bin", "HOME": "/home", "CUSTOM": "val"}
        result = filter_env_vars(EnvVarPolicy.INHERIT_NONE, base)
        assert result == {}

    def test_only_explicit_vars(self):
        base = {"PATH": "/usr/bin", "HOME": "/home"}
        result = filter_env_vars(EnvVarPolicy.INHERIT_NONE, base, {"MY_VAR": "val"})
        assert result == {"MY_VAR": "val"}


class TestFilterEdgeCases:
    def test_empty_base_env(self):
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, {})
        assert result == {}

    def test_none_explicit_vars(self):
        result = filter_env_vars(EnvVarPolicy.CORE_ONLY, {"PATH": "/usr/bin"}, None)
        assert "PATH" in result
