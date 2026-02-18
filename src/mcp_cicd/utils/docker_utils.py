"""
Docker SDK utilities for image building and container management.

Handles Docker client initialization, port conflict detection,
image building with log capture, and container lifecycle.
"""
import socket  # Verificación de disponibilidad de puertos TCP
from typing import Tuple, List, Optional, Dict, Any  # Type hints para tuplas, listas, opcionales

import docker  # Docker SDK para Python - interacción con Docker daemon
from docker.models.containers import Container  # Tipo de dato para contenedores Docker
from docker.models.images import Image  # Tipo de dato para imágenes Docker
from docker.errors import (  # Excepciones específicas del Docker SDK
    DockerException,
    BuildError,
    APIError,
    NotFound,
    ImageNotFound
)

from ..exceptions import (  # Excepciones personalizadas del proyecto
    DockerOperationError,
    BuildError as CustomBuildError,
    ContainerStartError,
    PortConflictError
)
from .logging import get_logger  # Logger estructurado

logger = get_logger(__name__)


def get_docker_client() -> docker.DockerClient:
    """
    Initialize Docker client from environment.

    Reads DOCKER_HOST, DOCKER_TLS_VERIFY, etc. from environment.

    Returns:
        Configured Docker client

    Raises:
        DockerOperationError: If Docker daemon is not accessible
    """
    try:
        client = docker.from_env()
        # Verify connection with a ping
        client.ping()
        logger.info("docker_client_initialized")
        return client
    except DockerException as e:
        raise DockerOperationError(
            f"Failed to connect to Docker daemon: {e}",
            context={"error": str(e)}
        )


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host address (default: 127.0.0.1 for localhost only)

    Returns:
        True if port is available, False if occupied
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(start: int = 8000, end: int = 9000) -> int:
    """
    Find the first available port in a range.

    Args:
        start: Start of port range (inclusive)
        end: End of port range (inclusive)

    Returns:
        First available port number

    Raises:
        PortConflictError: If no ports are available in range
    """
    for port in range(start, end + 1):
        if is_port_available(port):
            logger.debug("available_port_found", port=port)
            return port

    raise PortConflictError(
        f"No available ports in range {start}-{end}",
        context={"start": start, "end": end}
    )


def build_docker_image(
    client: docker.DockerClient,
    path: str,
    tag: str,
    dockerfile: str = "Dockerfile",
    buildargs: Optional[Dict[str, str]] = None
) -> Tuple[Image, List[str]]:
    """
    Build Docker image with log capture.

    Args:
        client: Docker client instance
        path: Build context path
        tag: Image tag (name:version)
        dockerfile: Dockerfile name (default: Dockerfile)
        buildargs: Optional build arguments

    Returns:
        Tuple of (Image object, build logs list)

    Raises:
        CustomBuildError: If build fails
    """
    build_logs = []

    try:
        logger.info(
            "docker_build_started",
            tag=tag,
            path=path,
            dockerfile=dockerfile
        )

        # Build image and capture logs
        image, log_generator = client.images.build(
            path=path,
            tag=tag,
            dockerfile=dockerfile,
            buildargs=buildargs or {},
            rm=True,  # Remove intermediate containers
            forcerm=True,  # Always remove intermediate containers
            labels={"managed-by": "mcp-cicd"},
            nocache=False
        )

        # Iterate log generator to completion (required for build to finish)
        for entry in log_generator:
            if "stream" in entry:
                line = entry["stream"].strip()
                if line:
                    build_logs.append(line)
                    logger.debug("build_log", line=line)
            elif "error" in entry:
                error_line = f"ERROR: {entry['error']}"
                build_logs.append(error_line)
                logger.error("build_error", error=entry["error"])

        logger.info(
            "docker_build_completed",
            tag=tag,
            image_id=image.id
        )

        return image, build_logs

    except BuildError as e:
        # Extract logs from BuildError exception
        error_logs = []
        if hasattr(e, 'build_log'):
            for entry in e.build_log:
                if "stream" in entry:
                    error_logs.append(entry["stream"].strip())

        all_logs = build_logs + error_logs

        logger.error(
            "docker_build_failed",
            tag=tag,
            error=str(e),
            logs_count=len(all_logs)
        )

        raise CustomBuildError(
            f"Docker build failed: {e.msg if hasattr(e, 'msg') else str(e)}",
            context={"tag": tag, "logs": all_logs}
        )

    except APIError as e:
        raise CustomBuildError(
            f"Docker API error during build: {e}",
            context={"tag": tag, "logs": build_logs}
        )


def cleanup_existing_container(
    client: docker.DockerClient,
    container_name: str
) -> None:
    """
    Stop and remove existing container if it exists.

    Args:
        client: Docker client instance
        container_name: Name of container to clean up
    """
    try:
        existing = client.containers.get(container_name)
        logger.info("stopping_existing_container", container=container_name)
        existing.stop(timeout=10)
        existing.remove()
        logger.info("existing_container_removed", container=container_name)
    except NotFound:
        # Container doesn't exist, nothing to clean up
        pass
    except APIError as e:
        logger.warning(
            "cleanup_failed",
            container=container_name,
            error=str(e)
        )


def deploy_container(
    client: docker.DockerClient,
    image_tag: str,
    container_name: str,
    host_port: int,
    container_port: int = 8000,
    env_vars: Optional[Dict[str, str]] = None
) -> Container:
    """
    Deploy container with security best practices.

    Args:
        client: Docker client instance
        image_tag: Image to deploy
        container_name: Unique container name
        host_port: Host port to bind to
        container_port: Container internal port
        env_vars: Optional environment variables

    Returns:
        Running container instance

    Raises:
        PortConflictError: If host port is already in use
        ContainerStartError: If container fails to start
    """
    # Verify port is available
    if not is_port_available(host_port):
        raise PortConflictError(
            f"Port {host_port} is already in use",
            context={"port": host_port}
        )

    # Clean up any existing container with same name
    cleanup_existing_container(client, container_name)

    try:
        logger.info(
            "deploying_container",
            image=image_tag,
            container=container_name,
            host_port=host_port,
            container_port=container_port
        )

        # Strip RUN_AS_USER if accidentally passed — container user is set by
        # the image itself; accepting it from env_vars would allow a caller to
        # force root execution and bypass no-new-privileges.
        safe_env = dict(env_vars or {})
        safe_env.pop("RUN_AS_USER", None)

        container = client.containers.run(
            image=image_tag,
            name=container_name,
            detach=True,  # Run in background
            ports={f"{container_port}/tcp": ("127.0.0.1", host_port)},  # Localhost only!
            environment=safe_env,
            labels={
                "managed-by": "mcp-cicd",
                "app": container_name
            },
            restart_policy={"Name": "unless-stopped"},
            mem_limit="512m",  # Memory limit
            security_opt=["no-new-privileges:true"],  # No privilege escalation
        )

        logger.info(
            "container_deployed",
            container_id=container.id,
            container_name=container_name
        )

        return container

    except APIError as e:
        error_msg = str(e)

        # Check for specific error conditions
        if "port is already allocated" in error_msg.lower():
            raise PortConflictError(
                f"Port {host_port} allocation failed: {e}",
                context={"port": host_port, "error": error_msg}
            )

        raise ContainerStartError(
            f"Failed to start container: {e}",
            context={
                "image": image_tag,
                "container": container_name,
                "error": error_msg
            }
        )


def get_container_logs(
    client: docker.DockerClient,
    container_name: str,
    tail: int = 100
) -> str:
    """
    Get container logs.

    Args:
        client: Docker client instance
        container_name: Container name
        tail: Number of lines to retrieve (default: 100)

    Returns:
        Container logs as string

    Raises:
        DockerOperationError: If container not found or logs unavailable
    """
    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=tail, timestamps=True)
        return logs.decode('utf-8')
    except NotFound:
        raise DockerOperationError(
            f"Container {container_name} not found",
            context={"container": container_name}
        )
    except APIError as e:
        raise DockerOperationError(
            f"Failed to get logs: {e}",
            context={"container": container_name, "error": str(e)}
        )


def stop_and_remove_container(
    client: docker.DockerClient,
    container_name: str
) -> None:
    """
    Stop and remove a container.

    Args:
        client: Docker client instance
        container_name: Container name to stop

    Raises:
        DockerOperationError: If operation fails
    """
    try:
        container = client.containers.get(container_name)
        logger.info("stopping_container", container=container_name)
        container.stop(timeout=10)
        container.remove()
        logger.info("container_removed", container=container_name)
    except NotFound:
        logger.warning("container_not_found", container=container_name)
    except APIError as e:
        raise DockerOperationError(
            f"Failed to stop container: {e}",
            context={"container": container_name, "error": str(e)}
        )
