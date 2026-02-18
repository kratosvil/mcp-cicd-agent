"""
Unit tests for config/settings.py

Tests configuration loading, validation, and directory creation.
"""
import pytest
from pydantic import ValidationError as PydanticValidationError

from mcp_cicd.config.settings import Settings


# ── Default values ──────────────────────────────────────────────────────────

def test_default_server_name():
    s = Settings(server_name="test-server")
    assert s.server_name == "test-server"


def test_default_transport():
    s = Settings()
    assert s.transport == "stdio"


def test_default_port_range():
    s = Settings()
    assert s.port_range_start == 8000
    assert s.port_range_end == 9000


def test_default_health_check_timeout():
    s = Settings()
    assert s.health_check_timeout == 30


def test_default_allowed_git_hosts():
    s = Settings()
    assert "github.com" in s.allowed_git_hosts
    assert "gitlab.com" in s.allowed_git_hosts


def test_github_token_defaults_none():
    s = Settings()
    assert s.github_token is None


# ── Log level validation ────────────────────────────────────────────────────

def test_log_level_normalized_to_uppercase():
    s = Settings(log_level="debug")
    assert s.log_level == "DEBUG"


def test_log_level_warning():
    s = Settings(log_level="warning")
    assert s.log_level == "WARNING"


def test_log_level_invalid_raises():
    with pytest.raises(PydanticValidationError):
        Settings(log_level="VERBOSE")


def test_log_level_empty_raises():
    with pytest.raises(PydanticValidationError):
        Settings(log_level="")


# ── Port range validation ───────────────────────────────────────────────────

def test_port_range_start_too_low_raises():
    with pytest.raises(PydanticValidationError):
        Settings(port_range_start=80)  # Privileged port


def test_port_range_end_too_low_raises():
    with pytest.raises(PydanticValidationError):
        Settings(port_range_end=1000)


def test_port_range_valid():
    s = Settings(port_range_start=9000, port_range_end=9500)
    assert s.port_range_start == 9000
    assert s.port_range_end == 9500


# ── ensure_directories ──────────────────────────────────────────────────────

def test_ensure_directories_creates_dirs(tmp_path):
    workspace = tmp_path / "ws"
    deployments = tmp_path / "dep"
    logs = tmp_path / "logs"

    s = Settings(workspace_dir=workspace, deployment_dir=deployments, log_dir=logs)
    s.ensure_directories()

    assert workspace.exists()
    assert deployments.exists()
    assert logs.exists()


def test_ensure_directories_idempotent(tmp_path):
    workspace = tmp_path / "ws"
    deployments = tmp_path / "dep"
    logs = tmp_path / "logs"

    s = Settings(workspace_dir=workspace, deployment_dir=deployments, log_dir=logs)
    s.ensure_directories()
    s.ensure_directories()  # second call must not raise

    assert workspace.exists()
