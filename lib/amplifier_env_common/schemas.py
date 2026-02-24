"""JSON schemas for the 8 common shape tools.

Each schema defines the input parameters the LLM must provide when calling the tool.
These are used by the tool's get_schema() method.
"""

ENV_READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to the file to read (relative to environment working directory)",
        },
        "offset": {
            "type": "integer",
            "description": "Line number to start reading from (1-indexed). Optional.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of lines to read. Optional.",
        },
    },
    "required": ["path"],
}

ENV_WRITE_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to write to (creates intermediate directories if needed)",
        },
        "content": {
            "type": "string",
            "description": "Content to write to the file",
        },
    },
    "required": ["path", "content"],
}

ENV_EDIT_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to the file to edit",
        },
        "old_string": {
            "type": "string",
            "description": "Exact string to find and replace (must be unique in the file)",
        },
        "new_string": {
            "type": "string",
            "description": "Replacement string",
        },
    },
    "required": ["path", "old_string", "new_string"],
}

ENV_EXEC_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "Shell command to execute",
        },
        "workdir": {
            "type": "string",
            "description": "Working directory for the command. Optional.",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds. Optional.",
        },
    },
    "required": ["command"],
}

ENV_GREP_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Regular expression pattern to search for",
        },
        "path": {
            "type": "string",
            "description": "Directory or file to search in. Optional (defaults to working directory).",
        },
        "glob": {
            "type": "string",
            "description": "Glob pattern to filter files (e.g., '*.py'). Optional.",
        },
        "type": {
            "type": "string",
            "description": "File type filter (e.g., 'py', 'js'). Optional.",
        },
    },
    "required": ["pattern"],
}

ENV_GLOB_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Glob pattern to match (e.g., '**/*.py')",
        },
        "path": {
            "type": "string",
            "description": "Base directory to search from. Optional.",
        },
    },
    "required": ["pattern"],
}

ENV_LIST_DIR_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Directory path to list. Defaults to working directory.",
        },
    },
    "required": [],
}

ENV_FILE_EXISTS_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to check for existence (file or directory)",
        },
    },
    "required": ["path"],
}
