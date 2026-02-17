"""
Input validation and sanitization utilities.

Prevents command injection and validates user inputs.
"""
import re  # Expresiones regulares para validación de patrones
from pathlib import Path  # Manejo moderno de rutas de archivos
from typing import List  # Type hints para listas

from ..exceptions import ValidationError  # Excepción personalizada para errores de validación
from .logging import get_logger  # Logger estructurado

logger = get_logger(__name__)


def validate_branch_name(branch: str) -> str:
    """
    Validate Git branch/tag/ref name.

    Args:
        branch: Branch name to validate

    Returns:
        Validated branch name

    Raises:
        ValidationError: If branch name is invalid
    """
    # Allow alphanumeric, dots, hyphens, underscores, slashes
    pattern = r'^[a-zA-Z0-9._\-/]+$'

    if not re.match(pattern, branch):
        raise ValidationError(
            f"Invalid branch name: {branch}",
            context={"branch": branch, "pattern": pattern}
        )

    # Prevent path traversal
    if '..' in branch:
        raise ValidationError(
            "Branch name cannot contain '..'",
            context={"branch": branch}
        )

    return branch


def validate_container_name(name: str) -> str:
    """
    Validate Docker container name.

    Args:
        name: Container name to validate

    Returns:
        Validated container name

    Raises:
        ValidationError: If container name is invalid
    """
    # Docker container names: alphanumeric, hyphens, underscores
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_\-]+$'

    if not re.match(pattern, name):
        raise ValidationError(
            f"Invalid container name: {name}",
            context={"name": name}
        )

    if len(name) > 63:
        raise ValidationError(
            "Container name too long (max 63 characters)",
            context={"name": name, "length": len(name)}
        )

    return name


def validate_image_tag(tag: str) -> str:
    """
    Validate Docker image tag.

    Args:
        tag: Image tag to validate (format: name:version)

    Returns:
        Validated image tag

    Raises:
        ValidationError: If image tag is invalid
    """
    # Basic format check
    if ':' in tag:
        name, version = tag.split(':', 1)
    else:
        name = tag
        version = 'latest'

    # Validate name part (lowercase, alphanumeric, dots, hyphens, slashes)
    name_pattern = r'^[a-z0-9][a-z0-9._\-/]*$'
    if not re.match(name_pattern, name):
        raise ValidationError(
            f"Invalid image name: {name}",
            context={"name": name}
        )

    # Validate version part (alphanumeric, dots, hyphens)
    version_pattern = r'^[a-zA-Z0-9._\-]+$'
    if not re.match(version_pattern, version):
        raise ValidationError(
            f"Invalid image version: {version}",
            context={"version": version}
        )

    return f"{name}:{version}"


def validate_port(port: int, min_port: int = 1024, max_port: int = 65535) -> int:
    """
    Validate port number.

    Args:
        port: Port number to validate
        min_port: Minimum allowed port (default: 1024 to avoid privileged ports)
        max_port: Maximum allowed port (default: 65535)

    Returns:
        Validated port number

    Raises:
        ValidationError: If port is out of valid range
    """
    if not isinstance(port, int):
        raise ValidationError(
            "Port must be an integer",
            context={"port": port, "type": type(port).__name__}
        )

    if not (min_port <= port <= max_port):
        raise ValidationError(
            f"Port must be between {min_port} and {max_port}",
            context={"port": port, "min": min_port, "max": max_port}
        )

    return port


def validate_dockerfile_path(path: str, base_dir: Path) -> Path:
    """
    Validate Dockerfile path and prevent directory traversal.

    Args:
        path: Dockerfile path (relative to base_dir)
        base_dir: Base directory containing the repository

    Returns:
        Validated absolute path

    Raises:
        ValidationError: If path is invalid or outside base directory
    """
    # Resolve to absolute path
    abs_path = (base_dir / path).resolve()

    # Ensure path is within base directory (prevent traversal)
    try:
        abs_path.relative_to(base_dir.resolve())
    except ValueError:
        raise ValidationError(
            "Dockerfile path is outside repository directory",
            context={"path": str(path), "base_dir": str(base_dir)}
        )

    # Check file exists
    if not abs_path.exists():
        raise ValidationError(
            "Dockerfile not found",
            context={"path": str(abs_path)}
        )

    # Check it's a file, not a directory
    if not abs_path.is_file():
        raise ValidationError(
            "Dockerfile path is not a file",
            context={"path": str(abs_path)}
        )

    return abs_path


def sanitize_environment_variables(env_vars: dict) -> dict:
    """
    Sanitize environment variables for Docker container.

    Args:
        env_vars: Dictionary of environment variables

    Returns:
        Sanitized environment variables

    Raises:
        ValidationError: If any variable contains dangerous values
    """
    sanitized = {}
    dangerous_patterns = [
        r'.*[;&|`$].*',  # Shell metacharacters
        r'.*\$\(.*\).*',  # Command substitution
        r'.*`.*`.*',  # Backtick command execution
    ]

    for key, value in env_vars.items():
        # Validate key
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
            raise ValidationError(
                f"Invalid environment variable name: {key}",
                context={"key": key}
            )

        # Check value for dangerous patterns
        value_str = str(value)
        for pattern in dangerous_patterns:
            if re.match(pattern, value_str):
                raise ValidationError(
                    f"Environment variable contains dangerous characters: {key}",
                    context={"key": key}
                )

        sanitized[key] = value_str

    return sanitized


def validate_deployment_id(deployment_id: str) -> str:
    """
    Validate deployment ID format.

    Args:
        deployment_id: Deployment ID to validate

    Returns:
        Validated deployment ID

    Raises:
        ValidationError: If deployment ID is invalid
    """
    # Expected format: dep-YYYYMMDD-XXXXXX
    pattern = r'^dep-\d{8}-[a-z0-9]+$'

    if not re.match(pattern, deployment_id):
        raise ValidationError(
            f"Invalid deployment ID format: {deployment_id}",
            context={"deployment_id": deployment_id, "expected_format": "dep-YYYYMMDD-XXXXXX"}
        )

    return deployment_id
