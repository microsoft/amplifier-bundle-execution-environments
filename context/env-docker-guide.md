# Environment Toolkit — Docker

Docker instances provide isolated containers. Pass `purpose` to select a base image.

## Creating Docker Instances

```
env_create(type="docker", name="build", purpose="python")
env_exec(instance="build", command="pip install -r requirements.txt")
env_exec(instance="build", command="pytest tests/")
env_destroy(instance="build")
```

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

Key parameters: `compose_files`, `compose_project`, `attach_to`, `health_check`.

## Cross-Session Sharing

Attach to an existing container created by another session:
```
env_create(type="docker", name="workspace", attach_to="container-id-from-parent")
```
Attached instances are not destroyed on session cleanup — the creating session owns them.
The `env_create` return value includes connection details (container_id, host, etc.).
