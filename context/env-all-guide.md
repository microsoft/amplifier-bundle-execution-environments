# Environment Toolkit

You have 11 `env_*` tools for working with local files, Docker containers, and remote SSH hosts.

## Key Concept: Instances

Every tool takes an `instance` parameter that targets a named environment. A **"local"** instance exists by default — no setup needed for host operations. Create additional instances on demand with `env_create`.

## Tools

| Tool | Purpose | Key Params |
|------|---------|------------|
| `env_create` | Create or attach to an environment | type, name, + compose_files, attach_to, health_check |
| `env_destroy` | Tear down an instance | instance |
| `env_list` | List all active instances | (none) |
| `env_exec` | Execute shell command | instance, command, timeout, workdir, env_vars |
| `env_read_file` | Read file content | instance, path, offset, limit |
| `env_write_file` | Write file content | instance, path, content |
| `env_edit_file` | Edit file (string replace) | instance, path, old_string, new_string |
| `env_grep` | Search file contents | instance, pattern, path, glob, case_insensitive, max_results |
| `env_glob` | Find files by pattern | instance, pattern, path |
| `env_list_dir` | List directory | instance, path, depth |
| `env_file_exists` | Check path exists | instance, path |

The `instance` parameter defaults to `"local"`, so simple calls just work on the host.

## Lifecycle: Create → Use → Destroy

1. **Local** — already there, use it directly
2. **Create** — `env_create(type="docker", name="build", purpose="python")` for isolation
3. **Use** — target by name: `env_exec(instance="build", command="pytest")`
4. **Destroy** — `env_destroy(instance="build")` when done (also auto-destroyed at session end)

Choose meaningful instance names: "build", "pi", "staging-db", "test-runner".

## Example Workflows

**Local only** (no setup needed):
```
env_exec(command="ls src/")
env_read_file(path="src/main.py")
env_edit_file(path="config.yaml", old_string="debug: false", new_string="debug: true")
```

**Docker isolation:**
```
env_create(type="docker", name="build", purpose="python")
env_exec(instance="build", command="pip install -r requirements.txt")
env_exec(instance="build", command="pytest tests/")
env_destroy(instance="build")
```

**Remote SSH:**
```
env_create(type="ssh", name="pi", host="voicebox")
env_exec(instance="pi", command="uname -a")
env_read_file(instance="pi", path="/etc/hostname")
env_destroy(instance="pi")
```

**Multi-environment:**
```
env_create(type="docker", name="build", purpose="rust")
env_create(type="ssh", name="deploy", host="staging.example.com")
env_exec(instance="build", command="cargo build --release")
env_exec(instance="deploy", command="systemctl restart app")
env_destroy(instance="build")
```

## Advanced Parameters

- **Environment variables:** `env_exec(instance="build", command="cargo build", env_vars={"RUST_LOG": "debug"})`
- **Recursive listing:** `env_list_dir(instance="build", path="src", depth=3)` (default depth=1)
- **Case-insensitive grep:** `env_grep(instance="local", pattern="TODO", case_insensitive=true, max_results=10)`
- **Execution timing:** `env_exec` results include `timed_out` (boolean) and `duration_ms` (wall-clock milliseconds)

## Compose Support

Bring up multi-service stacks and attach to a specific service:
```
env_create(type="docker", name="stack",
    compose_files=["docker-compose.yml"],
    compose_project="my-project",
    attach_to="web",
    health_check=true)
env_exec(instance="stack", command="python manage.py migrate")
env_destroy(instance="stack")  # runs compose down
```

## Cross-Session Sharing

Attach to an existing container created by another session:
```
env_create(type="docker", name="workspace", attach_to="container-id-from-parent")
```
Attached instances are not destroyed on session cleanup — the creating session owns them.
The `env_create` return value includes connection details (container_id, host, etc.).

## SSH Auto-Discovery

SSH credentials are auto-discovered when not explicitly provided:
```
env_create(type="ssh", name="pi", host="voicebox")
# Auto-discovers username and key from ~/.ssh/config and default keys
```
Explicit params always override auto-discovered values.

## Errors

- **Unknown instance** — error lists active instances so you can pick the right one
- **Docker without containers tool** — clear error explaining the dependency
- **SSH missing host** — clear error explaining required connection params
