"""
Unit tests for utils/docker_utils.py

Port-availability and port-finding functions are tested with real sockets.
Docker client and container operations use mocks.
"""
import socket
import pytest
from unittest.mock import MagicMock, patch

from docker.errors import APIError, NotFound

from mcp_cicd.exceptions import DockerOperationError, PortConflictError
from mcp_cicd.utils.docker_utils import (
    is_port_available,
    find_available_port,
    cleanup_existing_container,
    get_container_logs,
    stop_and_remove_container,
)


# ── is_port_available ───────────────────────────────────────────────────────

class TestIsPortAvailable:
    def test_available_port_returns_true(self):
        # Find a port that should be free
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        # Port is now released; should be available
        assert is_port_available(port) is True

    def test_occupied_port_returns_false(self):
        # Occupy a port temporarily
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            occupied_port = s.getsockname()[1]
            # While the socket is bound, the port should not be available
            result = is_port_available(occupied_port)
        assert result is False


# ── find_available_port ─────────────────────────────────────────────────────

class TestFindAvailablePort:
    def test_finds_port_in_range(self):
        port = find_available_port(9900, 9999)
        assert 9900 <= port <= 9999

    def test_raises_when_all_ports_occupied(self):
        """Patch is_port_available to always return False."""
        with patch("mcp_cicd.utils.docker_utils.is_port_available", return_value=False):
            with pytest.raises(PortConflictError):
                find_available_port(9990, 9991)

    def test_returns_first_available_port(self):
        """First port in range is the one returned when all are free."""
        with patch("mcp_cicd.utils.docker_utils.is_port_available", return_value=True):
            port = find_available_port(8500, 8600)
        assert port == 8500


# ── cleanup_existing_container ──────────────────────────────────────────────

class TestCleanupExistingContainer:
    def test_stops_and_removes_existing_container(self):
        container_mock = MagicMock()
        client_mock = MagicMock()
        client_mock.containers.get.return_value = container_mock

        cleanup_existing_container(client_mock, "my-container")

        container_mock.stop.assert_called_once_with(timeout=10)
        container_mock.remove.assert_called_once()

    def test_silently_ignores_not_found(self):
        client_mock = MagicMock()
        client_mock.containers.get.side_effect = NotFound("not found")

        # Should not raise
        cleanup_existing_container(client_mock, "missing-container")

    def test_logs_warning_on_api_error(self):
        client_mock = MagicMock()
        container_mock = MagicMock()
        client_mock.containers.get.return_value = container_mock
        container_mock.stop.side_effect = APIError("API error")

        # Should not raise (logs warning instead)
        cleanup_existing_container(client_mock, "my-container")


# ── get_container_logs ──────────────────────────────────────────────────────

class TestGetContainerLogs:
    def test_returns_decoded_logs(self):
        client_mock = MagicMock()
        container_mock = MagicMock()
        client_mock.containers.get.return_value = container_mock
        container_mock.logs.return_value = b"2026-02-18 Starting server\n2026-02-18 Ready\n"

        result = get_container_logs(client_mock, "my-container", tail=50)

        assert "Starting server" in result
        assert "Ready" in result
        container_mock.logs.assert_called_once_with(tail=50, timestamps=True)

    def test_raises_on_not_found(self):
        client_mock = MagicMock()
        client_mock.containers.get.side_effect = NotFound("not found")

        with pytest.raises(DockerOperationError):
            get_container_logs(client_mock, "missing-container")

    def test_raises_on_api_error(self):
        client_mock = MagicMock()
        container_mock = MagicMock()
        client_mock.containers.get.return_value = container_mock
        container_mock.logs.side_effect = APIError("error")

        with pytest.raises(DockerOperationError):
            get_container_logs(client_mock, "my-container")


# ── stop_and_remove_container ───────────────────────────────────────────────

class TestStopAndRemoveContainer:
    def test_stops_and_removes(self):
        client_mock = MagicMock()
        container_mock = MagicMock()
        client_mock.containers.get.return_value = container_mock

        stop_and_remove_container(client_mock, "my-container")

        container_mock.stop.assert_called_once_with(timeout=10)
        container_mock.remove.assert_called_once()

    def test_silently_handles_not_found(self):
        client_mock = MagicMock()
        client_mock.containers.get.side_effect = NotFound("not found")

        # Should not raise
        stop_and_remove_container(client_mock, "gone-container")

    def test_raises_on_api_error(self):
        client_mock = MagicMock()
        container_mock = MagicMock()
        client_mock.containers.get.return_value = container_mock
        container_mock.stop.side_effect = APIError("daemon error")

        with pytest.raises(DockerOperationError):
            stop_and_remove_container(client_mock, "my-container")


# ── get_docker_client ───────────────────────────────────────────────────────

class TestGetDockerClient:
    def test_raises_when_daemon_unreachable(self):
        from docker.errors import DockerException

        with patch("mcp_cicd.utils.docker_utils.docker.from_env") as mock_from_env:
            mock_from_env.side_effect = DockerException("Cannot connect to Docker")
            with pytest.raises(DockerOperationError):
                from mcp_cicd.utils.docker_utils import get_docker_client
                get_docker_client()

    def test_raises_when_ping_fails(self):
        from docker.errors import DockerException

        with patch("mcp_cicd.utils.docker_utils.docker.from_env") as mock_from_env:
            client_mock = MagicMock()
            client_mock.ping.side_effect = DockerException("Ping failed")
            mock_from_env.return_value = client_mock
            with pytest.raises(DockerOperationError):
                from mcp_cicd.utils.docker_utils import get_docker_client
                get_docker_client()
