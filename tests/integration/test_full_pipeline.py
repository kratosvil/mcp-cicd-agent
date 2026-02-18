"""
Integration tests for the full MCP CI/CD deployment pipeline.

Requires Docker Desktop running.
Tests all 8 pipeline steps using the minimal fixture app in tests/fixtures/simple-app/.

Run with:
    pytest tests/integration/ -v -s
"""
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from mcp_cicd.utils.docker_utils import (
    build_docker_image,
    deploy_container as deploy_container_util,
    get_container_logs,
    stop_and_remove_container,
    find_available_port,
    is_port_available,
)
from mcp_cicd.utils.state_manager import StateManager
from mcp_cicd.models.deployment import DeploymentRecord, DeploymentStatus

# ── Configuration ────────────────────────────────────────────────────────────
TEST_IMAGE_TAG = "mcp-cicd-test-app:test"
FIXTURE_APP_PATH = Path(__file__).parent.parent / "fixtures" / "simple-app"
CONTAINER_PORT = 8000
HEALTHCHECK_TIMEOUT = 60  # seconds


# ── Helpers ──────────────────────────────────────────────────────────────────

def wait_for_health(url: str, timeout: int = HEALTHCHECK_TIMEOUT) -> bool:
    """Poll URL until it returns 200 or timeout is reached."""
    deadline = time.monotonic() + timeout
    interval = 1.0
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=3.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
        interval = min(interval * 1.5, 5.0)
    return False


# ── Module-scoped image fixture ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def built_image(docker_client):
    """
    Build the test Docker image ONCE for the entire test module.
    All tests that need a Docker image use this fixture.
    Teardown removes the image after all module tests complete.
    """
    client = docker_client
    image, logs = build_docker_image(
        client=client,
        path=str(FIXTURE_APP_PATH),
        tag=TEST_IMAGE_TAG,
        dockerfile="Dockerfile",
    )
    assert image is not None, "Image build returned None"
    yield image

    # Module teardown: remove all mcp-cicd containers first, then image
    try:
        for c in client.containers.list(
            all=True, filters={"label": "managed-by=mcp-cicd"}
        ):
            try:
                c.stop(timeout=5)
                c.remove(force=True)
            except Exception:
                pass
    except Exception:
        pass
    try:
        client.images.remove(TEST_IMAGE_TAG, force=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — detect_project_type (filesystem detection, no Docker needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStep1DetectProjectType:
    """Tests detect_project_type logic against the fixture app files."""

    def test_detects_docker_project(self):
        path = FIXTURE_APP_PATH
        assert (path / "Dockerfile").exists(), "Fixture Dockerfile missing"

        detection_rules = [
            (["docker-compose.yml", "docker-compose.yaml", "compose.yml"], "docker-compose"),
            (["Dockerfile"], "docker"),
            (["package.json"], "nodejs"),
            (["requirements.txt", "pyproject.toml", "setup.py"], "python"),
            (["go.mod"], "go"),
            (["Cargo.toml"], "rust"),
        ]
        project_type = "unknown"
        for markers, ptype in detection_rules:
            for marker in markers:
                if (path / marker).exists():
                    project_type = ptype
                    break
            if project_type != "unknown":
                break

        assert project_type == "docker"

    def test_detects_exposed_port_8000(self):
        dockerfile_path = FIXTURE_APP_PATH / "Dockerfile"
        content = dockerfile_path.read_text()
        assert "EXPOSE 8000" in content

    def test_has_no_compose_file(self):
        for fname in ["docker-compose.yml", "docker-compose.yaml", "compose.yml"]:
            assert not (FIXTURE_APP_PATH / fname).exists()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — build_image
# ═══════════════════════════════════════════════════════════════════════════════

class TestStep2BuildImage:
    def test_build_produces_image_with_id(self, built_image):
        assert built_image.id is not None
        assert built_image.id.startswith("sha256:")

    def test_image_registered_in_docker(self, docker_client, built_image):
        images = docker_client.images.list(name=TEST_IMAGE_TAG)
        assert len(images) >= 1

    def test_image_has_correct_tag(self, docker_client, built_image):
        images = docker_client.images.list(name=TEST_IMAGE_TAG)
        all_tags = [t for img in images for t in img.tags]
        assert TEST_IMAGE_TAG in all_tags

    def test_image_has_mcp_cicd_label(self, docker_client, built_image):
        images = docker_client.images.list(name=TEST_IMAGE_TAG)
        assert len(images) >= 1
        assert images[0].labels.get("managed-by") == "mcp-cicd"

    def test_build_fails_with_missing_dockerfile(self, docker_client, tmp_path):
        """Build must raise when Dockerfile is absent from the build context."""
        from mcp_cicd.exceptions import BuildError
        with pytest.raises((BuildError, Exception)):
            build_docker_image(
                client=docker_client,
                path=str(tmp_path),
                tag="should-fail:test",
                dockerfile="Dockerfile",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — deploy_container
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def deployed_container(docker_client, built_image):
    """Deploy a fresh container for each test that needs one."""
    host_port = find_available_port(9200, 9299)
    name = "mcp-cicd-test-deploy"

    container = deploy_container_util(
        client=docker_client,
        image_tag=TEST_IMAGE_TAG,
        container_name=name,
        host_port=host_port,
        container_port=CONTAINER_PORT,
    )
    container.reload()
    yield {"container": container, "host_port": host_port, "name": name}

    try:
        stop_and_remove_container(docker_client, name)
    except Exception:
        pass


class TestStep3DeployContainer:
    def test_container_is_running(self, deployed_container):
        c = deployed_container["container"]
        c.reload()
        assert c.status == "running"

    def test_container_bound_to_localhost_only(self, deployed_container):
        c = deployed_container["container"]
        c.reload()
        bindings = c.ports.get(f"{CONTAINER_PORT}/tcp", [])
        assert len(bindings) > 0
        host_ip = bindings[0]["HostIp"]
        assert host_ip in ("127.0.0.1", ""), (
            f"Container NOT bound to localhost only! Got: {host_ip}"
        )

    def test_container_has_mcp_cicd_label(self, deployed_container):
        c = deployed_container["container"]
        c.reload()
        assert c.labels.get("managed-by") == "mcp-cicd"

    def test_port_conflict_raises(self, deployed_container, docker_client, built_image):
        from mcp_cicd.exceptions import PortConflictError
        host_port = deployed_container["host_port"]
        with pytest.raises(PortConflictError):
            deploy_container_util(
                client=docker_client,
                image_tag=TEST_IMAGE_TAG,
                container_name="mcp-cicd-test-conflict",
                host_port=host_port,
                container_port=CONTAINER_PORT,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — healthcheck
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def live_container(docker_client, built_image):
    """Deploy a container and expose it for healthcheck tests."""
    host_port = find_available_port(9300, 9399)
    name = "mcp-cicd-health-test"

    container = deploy_container_util(
        client=docker_client,
        image_tag=TEST_IMAGE_TAG,
        container_name=name,
        host_port=host_port,
        container_port=CONTAINER_PORT,
    )
    container.reload()
    yield {"container": container, "host_port": host_port}

    try:
        stop_and_remove_container(docker_client, name)
    except Exception:
        pass


class TestStep4Healthcheck:
    def test_health_endpoint_returns_200(self, live_container):
        host_port = live_container["host_port"]
        healthy = wait_for_health(f"http://localhost:{host_port}/health")
        assert healthy, "Health endpoint did not return 200 within timeout"

    def test_root_endpoint_returns_200(self, live_container):
        host_port = live_container["host_port"]
        healthy = wait_for_health(f"http://localhost:{host_port}/")
        assert healthy

    def test_health_response_body_is_ok(self, live_container):
        host_port = live_container["host_port"]
        url = f"http://localhost:{host_port}/health"
        wait_for_health(url)
        resp = httpx.get(url, timeout=5.0)
        assert resp.text == "OK"


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — get_logs
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def container_with_traffic(docker_client, built_image):
    """Container that has received HTTP requests so logs are non-empty."""
    host_port = find_available_port(9400, 9499)
    name = "mcp-cicd-logs-test"

    container = deploy_container_util(
        client=docker_client,
        image_tag=TEST_IMAGE_TAG,
        container_name=name,
        host_port=host_port,
        container_port=CONTAINER_PORT,
    )
    container.reload()

    # Wait for the server to be ready, then generate some log entries
    wait_for_health(f"http://localhost:{host_port}/health")
    for _ in range(3):
        try:
            httpx.get(f"http://localhost:{host_port}/health", timeout=3.0)
        except Exception:
            pass

    yield {"container": container, "host_port": host_port, "name": name}

    try:
        stop_and_remove_container(docker_client, name)
    except Exception:
        pass


class TestStep5GetLogs:
    def test_get_logs_returns_string(self, container_with_traffic, docker_client):
        logs = get_container_logs(docker_client, container_with_traffic["name"], tail=100)
        assert isinstance(logs, str)

    def test_logs_contain_startup_message(self, container_with_traffic, docker_client):
        logs = get_container_logs(docker_client, container_with_traffic["name"], tail=200)
        assert "Server started on port 8000" in logs

    def test_get_logs_missing_container_raises(self, docker_client, built_image):
        from mcp_cicd.exceptions import DockerOperationError
        with pytest.raises(DockerOperationError):
            get_container_logs(docker_client, "totally-nonexistent-xyz-abc")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 — stop_deployment
# ═══════════════════════════════════════════════════════════════════════════════

class TestStep6StopDeployment:
    def test_stop_removes_container(self, docker_client, built_image):
        host_port = find_available_port(9500, 9599)
        name = "mcp-cicd-stop-test"

        container = deploy_container_util(
            client=docker_client,
            image_tag=TEST_IMAGE_TAG,
            container_name=name,
            host_port=host_port,
            container_port=CONTAINER_PORT,
        )
        container.reload()
        assert container.status == "running"

        stop_and_remove_container(docker_client, name)

        from docker.errors import NotFound
        with pytest.raises(NotFound):
            docker_client.containers.get(name)

    def test_stop_frees_port(self, docker_client, built_image):
        host_port = find_available_port(9600, 9699)
        name = "mcp-cicd-port-free-test"

        deploy_container_util(
            client=docker_client,
            image_tag=TEST_IMAGE_TAG,
            container_name=name,
            host_port=host_port,
            container_port=CONTAINER_PORT,
        )
        time.sleep(1)
        stop_and_remove_container(docker_client, name)
        time.sleep(1)

        assert is_port_available(host_port), f"Port {host_port} NOT freed after stop"

    def test_stop_nonexistent_container_does_not_raise(self, docker_client):
        stop_and_remove_container(docker_client, "totally-nonexistent-xyz-container")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7 — StateManager (deployment state persistence)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_record(
    dep_id: str,
    status: DeploymentStatus,
    repo_url: str = "https://github.com/test/app.git",
    image_tag: str = TEST_IMAGE_TAG,
    container_name: str = "mcp-cicd-state-test",
    host_port: int = 8500,
) -> DeploymentRecord:
    return DeploymentRecord(
        deployment_id=dep_id,
        repo_url=repo_url,
        branch="main",
        commit_sha="a" * 40,
        project_type="docker",
        image_name="mcp-cicd-test-app",
        image_tag=image_tag,
        container_name=container_name,
        host_port=host_port,
        container_port=CONTAINER_PORT,
        status=status,
        created_at=datetime.now(tz=timezone.utc),
    )


class TestStep7StateManager:
    def test_save_and_load(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        sm.save(_make_record("dep-20260218-aabbcc", DeploymentStatus.RUNNING))
        loaded = sm.load("dep-20260218-aabbcc")
        assert loaded is not None
        assert loaded.deployment_id == "dep-20260218-aabbcc"
        assert loaded.status == DeploymentStatus.RUNNING

    def test_load_nonexistent_returns_none(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        assert sm.load("dep-20000101-xxxxxx") is None

    def test_find_latest_successful(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        repo = "https://github.com/test/find-test.git"
        sm.save(_make_record("dep-20260218-run001", DeploymentStatus.RUNNING, repo_url=repo))
        sm.save(_make_record("dep-20260218-fail01", DeploymentStatus.FAILED, repo_url=repo))
        result = sm.find_latest_successful(repo_url=repo)
        assert result is not None
        assert result.deployment_id == "dep-20260218-run001"

    def test_find_excludes_given_id(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        repo = "https://github.com/test/exclude-test.git"
        sm.save(_make_record("dep-20260218-run010", DeploymentStatus.RUNNING, repo_url=repo))
        result = sm.find_latest_successful(repo_url=repo, exclude="dep-20260218-run010")
        assert result is None

    def test_find_returns_none_when_no_successful(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        repo = "https://github.com/test/no-success.git"
        sm.save(_make_record("dep-20260218-fail99", DeploymentStatus.FAILED, repo_url=repo))
        assert sm.find_latest_successful(repo_url=repo) is None

    def test_list_all_includes_all_deployments(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        sm.save(_make_record("dep-20260218-lst001", DeploymentStatus.RUNNING))
        sm.save(_make_record("dep-20260218-lst002", DeploymentStatus.STOPPED))
        ids = [d["deployment_id"] for d in sm.list_all()]
        assert "dep-20260218-lst001" in ids
        assert "dep-20260218-lst002" in ids

    def test_save_overwrites_same_id(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        r = _make_record("dep-20260218-upd001", DeploymentStatus.RUNNING)
        sm.save(r)
        r.status = DeploymentStatus.STOPPED
        sm.save(r)
        loaded = sm.load("dep-20260218-upd001")
        assert loaded.status == DeploymentStatus.STOPPED


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8 — Rollback (deploy previous image + state verification)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStep8Rollback:
    """
    Full rollback test:
    1. Deploy v1 → mark RUNNING in state
    2. Stop v1
    3. Deploy v2 → mark FAILED in state
    4. Find v1 as previous successful deployment
    5. Stop v2, redeploy v1 image (rollback)
    6. Verify rollback container is healthy
    """

    @pytest.fixture()
    def rollback_scenario(self, docker_client, built_image, tmp_path):
        client = docker_client
        sm = StateManager(tmp_path / "rollback-state")
        repo_url = "https://github.com/test/rollback-app.git"
        host_port = find_available_port(9700, 9799)

        # ── Deploy v1 (the "previous good" version) ─────────────────────────
        v1_name = "mcp-cicd-rollback-v1"
        container_v1 = deploy_container_util(
            client=client, image_tag=TEST_IMAGE_TAG,
            container_name=v1_name, host_port=host_port,
            container_port=CONTAINER_PORT,
        )
        container_v1.reload()
        sm.save(DeploymentRecord(
            deployment_id="dep-20260218-v1good1",
            repo_url=repo_url, branch="main",
            commit_sha="1" * 40, project_type="docker",
            image_name="mcp-cicd-test-app", image_tag=TEST_IMAGE_TAG,
            image_id=container_v1.image.id, container_name=v1_name,
            container_id=container_v1.id, host_port=host_port,
            container_port=CONTAINER_PORT, status=DeploymentStatus.RUNNING,
            created_at=datetime.now(tz=timezone.utc),
        ))

        # ── Stop v1, deploy v2 (the "failed" version) ───────────────────────
        stop_and_remove_container(client, v1_name)
        time.sleep(1)

        v2_name = "mcp-cicd-rollback-v2"
        container_v2 = deploy_container_util(
            client=client, image_tag=TEST_IMAGE_TAG,
            container_name=v2_name, host_port=host_port,
            container_port=CONTAINER_PORT,
        )
        container_v2.reload()
        sm.save(DeploymentRecord(
            deployment_id="dep-20260218-v2fail1",
            repo_url=repo_url, branch="main",
            commit_sha="2" * 40, project_type="docker",
            image_name="mcp-cicd-test-app", image_tag=TEST_IMAGE_TAG,
            image_id=container_v2.image.id, container_name=v2_name,
            container_id=container_v2.id, host_port=host_port,
            container_port=CONTAINER_PORT, status=DeploymentStatus.FAILED,
            created_at=datetime.now(tz=timezone.utc),
        ))

        yield {
            "client": client, "sm": sm, "repo_url": repo_url,
            "host_port": host_port,
            "record_v2_id": "dep-20260218-v2fail1", "v2_name": v2_name,
        }

        for name in [v1_name, v2_name, "mcp-cicd-rollback-restored"]:
            try:
                stop_and_remove_container(client, name)
            except Exception:
                pass

    def test_state_manager_finds_previous_successful(self, rollback_scenario):
        sm = rollback_scenario["sm"]
        repo_url = rollback_scenario["repo_url"]
        exclude = rollback_scenario["record_v2_id"]

        previous = sm.find_latest_successful(repo_url=repo_url, exclude=exclude)
        assert previous is not None
        assert previous.deployment_id == "dep-20260218-v1good1"

    def test_rollback_redeploys_and_is_healthy(self, rollback_scenario):
        client = rollback_scenario["client"]
        sm = rollback_scenario["sm"]
        repo_url = rollback_scenario["repo_url"]
        host_port = rollback_scenario["host_port"]
        v2_name = rollback_scenario["v2_name"]
        exclude = rollback_scenario["record_v2_id"]

        previous = sm.find_latest_successful(repo_url=repo_url, exclude=exclude)
        assert previous is not None

        # Stop the "failed" v2 container
        stop_and_remove_container(client, v2_name)
        time.sleep(1)

        # Redeploy v1 image as rollback
        rollback_container = deploy_container_util(
            client=client,
            image_tag=previous.image_tag,
            container_name="mcp-cicd-rollback-restored",
            host_port=host_port,
            container_port=previous.container_port,
        )
        rollback_container.reload()
        assert rollback_container.status == "running"

        # Verify the rolled-back service is healthy
        healthy = wait_for_health(f"http://localhost:{host_port}/health")
        assert healthy, "Rolled-back container not healthy"

    def test_rollback_no_previous_returns_none(self, tmp_deployment_dir):
        sm = StateManager(tmp_deployment_dir)
        result = sm.find_latest_successful(
            repo_url="https://github.com/test/nonexistent.git"
        )
        assert result is None
