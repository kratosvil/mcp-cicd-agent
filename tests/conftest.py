"""
Shared pytest fixtures for MCP CI/CD Agent test suite.
"""
from pathlib import Path

import pytest
import docker
from docker.errors import DockerException

# ── Constants ──────────────────────────────────────────────────────────────
FIXTURE_APP_PATH = Path(__file__).parent / "fixtures" / "simple-app"
TEST_IMAGE_TAG = "mcp-cicd-test-app:test"
TEST_CONTAINER_NAME = "mcp-cicd-test-container"


# ── Docker availability ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def docker_available():
    """Returns True if Docker daemon is accessible."""
    try:
        client = docker.from_env()
        client.ping()
        client.close()
        return True
    except DockerException:
        return False


@pytest.fixture(scope="session")
def docker_client(docker_available):
    """Authenticated Docker client; skips all tests if Docker is unavailable."""
    if not docker_available:
        pytest.skip("Docker daemon not accessible — skipping Docker tests")
    client = docker.from_env()
    yield client
    client.close()


# ── Fixture app paths ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fixture_app_path():
    """Absolute path to the minimal test application (with Dockerfile)."""
    return FIXTURE_APP_PATH


@pytest.fixture
def test_image_tag():
    return TEST_IMAGE_TAG


@pytest.fixture
def test_container_name():
    return TEST_CONTAINER_NAME


# ── Temp directories ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_deployment_dir(tmp_path):
    """Temporary directory for deployment state JSON files."""
    d = tmp_path / "deployments"
    d.mkdir()
    return d


@pytest.fixture
def tmp_workspace_dir(tmp_path):
    """Temporary directory for git workspace clones."""
    d = tmp_path / "workspace"
    d.mkdir()
    return d


# ── Docker cleanup ──────────────────────────────────────────────────────────

@pytest.fixture
def cleanup_test_containers(docker_client):
    """
    Teardown fixture: stops and removes any containers/images
    created during the integration tests (identified by 'managed-by=mcp-cicd' label).
    Use this explicitly on tests that deploy containers.
    """
    yield
    # Stop/remove all mcp-cicd managed containers
    try:
        for container in docker_client.containers.list(
            all=True, filters={"label": "managed-by=mcp-cicd"}
        ):
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except Exception:
                pass
    except Exception:
        pass

    # Remove test image
    try:
        docker_client.images.remove(TEST_IMAGE_TAG, force=True)
    except Exception:
        pass
