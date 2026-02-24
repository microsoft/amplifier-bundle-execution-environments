"""Tests for env-common shared schemas."""

from amplifier_env_common.schemas import (
    ENV_EDIT_FILE_SCHEMA,
    ENV_EXEC_SCHEMA,
    ENV_FILE_EXISTS_SCHEMA,
    ENV_GLOB_SCHEMA,
    ENV_GREP_SCHEMA,
    ENV_LIST_DIR_SCHEMA,
    ENV_READ_FILE_SCHEMA,
    ENV_WRITE_FILE_SCHEMA,
)


class TestSchemaStructure:
    """Verify all 8 schemas exist and have correct required fields."""

    def test_read_file_schema(self):
        assert ENV_READ_FILE_SCHEMA["type"] == "object"
        assert "path" in ENV_READ_FILE_SCHEMA["properties"]
        assert "path" in ENV_READ_FILE_SCHEMA["required"]

    def test_write_file_schema(self):
        assert "path" in ENV_WRITE_FILE_SCHEMA["required"]
        assert "content" in ENV_WRITE_FILE_SCHEMA["required"]

    def test_edit_file_schema(self):
        assert "path" in ENV_EDIT_FILE_SCHEMA["required"]
        assert "old_string" in ENV_EDIT_FILE_SCHEMA["required"]
        assert "new_string" in ENV_EDIT_FILE_SCHEMA["required"]

    def test_exec_schema(self):
        assert "command" in ENV_EXEC_SCHEMA["required"]
        assert "workdir" in ENV_EXEC_SCHEMA["properties"]
        assert "timeout" in ENV_EXEC_SCHEMA["properties"]

    def test_grep_schema(self):
        assert "pattern" in ENV_GREP_SCHEMA["required"]

    def test_glob_schema(self):
        assert "pattern" in ENV_GLOB_SCHEMA["required"]

    def test_list_dir_schema(self):
        assert ENV_LIST_DIR_SCHEMA["required"] == []

    def test_file_exists_schema(self):
        assert "path" in ENV_FILE_EXISTS_SCHEMA["required"]

    def test_all_schemas_are_objects(self):
        schemas = [
            ENV_READ_FILE_SCHEMA,
            ENV_WRITE_FILE_SCHEMA,
            ENV_EDIT_FILE_SCHEMA,
            ENV_EXEC_SCHEMA,
            ENV_GREP_SCHEMA,
            ENV_GLOB_SCHEMA,
            ENV_LIST_DIR_SCHEMA,
            ENV_FILE_EXISTS_SCHEMA,
        ]
        for schema in schemas:
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema
