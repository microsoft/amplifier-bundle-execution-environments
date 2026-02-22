"""Integration test configuration for Phase 4 end-to-end tests.

Supports two integration test categories:

Docker tests (Phase 4 Docker backend):
    pytest env-all/tests/integration/ -v --docker-integration

SSH tests (Phase 4 SSH backend):
    pytest env-all/tests/integration/ -v --ssh-integration
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# pytest hooks: --docker-integration and --ssh-integration flags
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    # Guard against duplicate registration when multiple integration conftest
    # files are collected in the same pytest run (e.g., make test).
    try:
        parser.addoption(
            "--docker-integration",
            action="store_true",
            default=False,
            help="Run Docker integration tests (requires Docker daemon)",
        )
    except ValueError:
        pass  # Already registered by another conftest

    try:
        parser.addoption(
            "--ssh-integration",
            action="store_true",
            default=False,
            help="Run SSH integration tests (requires Docker daemon for sshd)",
        )
    except ValueError:
        pass  # Already registered by another conftest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "docker_integration: marks tests that require a running Docker daemon",
    )
    config.addinivalue_line(
        "markers",
        "ssh_integration: marks tests that require a running sshd container",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--docker-integration"):
        skip_docker = pytest.mark.skip(reason="Need --docker-integration to run")
        for item in items:
            if "docker_integration" in item.keywords:
                item.add_marker(skip_docker)

    if not config.getoption("--ssh-integration"):
        skip_ssh = pytest.mark.skip(reason="Need --ssh-integration to run")
        for item in items:
            if "ssh_integration" in item.keywords:
                item.add_marker(skip_ssh)


# ---------------------------------------------------------------------------
# Docker availability check
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Check whether the Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# sshd container fixture (same pattern as env-ssh/tests/integration/conftest.py)
# ---------------------------------------------------------------------------

_SSHD_IMAGE = "lscr.io/linuxserver/openssh-server:latest"
_SSHD_USER = "linuxserver.io"


@pytest.fixture(scope="session")
def sshd_container(request):
    """Start a Docker container running sshd with an ephemeral SSH key.

    Yields a dict with connection details:
        host: str        — always "127.0.0.1"
        port: int        — mapped host port for sshd
        username: str    — SSH username
        key_file: str    — path to ephemeral private key
        known_hosts: str — path to known_hosts file

    Tears down the container in the finally block.
    Skips the entire session if Docker is not available.
    """
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    tmpdir = tempfile.mkdtemp(prefix="ssh-phase4-integration-")
    key_file = os.path.join(tmpdir, "test_key")
    pub_file = key_file + ".pub"
    known_hosts_file = os.path.join(tmpdir, "known_hosts")
    container_name = f"sshd-phase4-{uuid.uuid4().hex[:12]}"

    try:
        # 1. Generate ephemeral ed25519 key pair
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", key_file, "-N", "", "-q"],
            check=True,
            timeout=10,
        )
        pub_key = open(pub_file).read().strip()

        # 2. Start sshd container with the public key injected
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "-e",
                f"PUBLIC_KEY={pub_key}",
                "-e",
                f"USER_NAME={_SSHD_USER}",
                "-e",
                "SUDO_ACCESS=true",
                "-p",
                "0:2222",  # map container port 2222 to random host port
                _SSHD_IMAGE,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            pytest.skip(f"Failed to start sshd container: {result.stderr.strip()}")

        # 3. Discover the mapped host port
        port_result = subprocess.run(
            [
                "docker",
                "port",
                container_name,
                "2222",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Output like "0.0.0.0:32771" or "[::]:32771"
        port_line = port_result.stdout.strip().splitlines()[0]
        host_port = int(port_line.rsplit(":", 1)[1])

        # 4. Wait for sshd to be ready (poll with pgrep inside container)
        deadline = time.monotonic() + 30
        ready = False
        while time.monotonic() < deadline:
            check = subprocess.run(
                ["docker", "exec", container_name, "pgrep", "-f", "sshd"],
                capture_output=True,
                timeout=5,
            )
            if check.returncode == 0:
                ready = True
                break
            time.sleep(1)

        if not ready:
            pytest.skip("sshd did not become ready within 30 seconds")

        # Small extra delay for key setup to complete
        time.sleep(2)

        # 5. Scan the server's host key into a known_hosts file
        scan = subprocess.run(
            ["ssh-keyscan", "-p", str(host_port), "127.0.0.1"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if scan.returncode != 0 or not scan.stdout.strip():
            pytest.skip(f"ssh-keyscan failed: {scan.stderr.strip()}")
        with open(known_hosts_file, "w") as fh:
            fh.write(scan.stdout)

        yield {
            "host": "127.0.0.1",
            "port": host_port,
            "username": _SSHD_USER,
            "key_file": key_file,
            "known_hosts": known_hosts_file,
        }

    finally:
        # 6. Tear down container
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=30,
        )
        # Clean up temp files
        for f in (key_file, pub_file, known_hosts_file):
            try:
                os.unlink(f)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
