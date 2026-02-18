# Este archivo implementa las herramientas MCP para operaciones Docker:
# construcción de imágenes, despliegue de contenedores y obtención de logs.

"""
MCP tools for Docker operations.

Implements build_image, deploy_container, and get_logs tools.
"""
from datetime import datetime  # Manejo de fechas y timestamps
from pathlib import Path  # Manejo moderno de rutas de archivos
from typing import Optional, Dict  # Type hints para valores opcionales y diccionarios

from mcp.server.fastmcp import FastMCP  # Framework FastMCP para registro de herramientas

from ..config.settings import get_settings  # Singleton de configuración
from ..utils.docker_utils import (  # Funciones de Docker SDK
    get_docker_client,
    build_docker_image,
    deploy_container as deploy_container_util,
    get_container_logs,
    find_available_port,
    is_port_available
)
from ..utils.validation import (  # Funciones de validación de inputs
    validate_image_tag,
    validate_container_name,
    validate_port,
    validate_dockerfile_path
)
from ..utils.logging import get_logger  # Logger estructurado
from ..utils.state_manager import StateManager  # Persistencia de estado de deployments
from ..models.deployment import DeploymentRecord, DeploymentStatus  # Modelos de deployment
from ..exceptions import (  # Excepciones personalizadas
    DockerOperationError,
    BuildError,
    ContainerStartError,
    PortConflictError,
    ValidationError
)

logger = get_logger(__name__)
settings = get_settings()


def register_docker_tools(mcp: FastMCP) -> None:
    """
    Register Docker-related MCP tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    async def build_image(
        path: str,
        image_tag: str,
        dockerfile: str = "Dockerfile",
        build_args: Optional[Dict[str, str]] = None
    ) -> dict:
        """
        Build Docker image with log capture.

        Builds a Docker image from a Dockerfile in the specified path,
        capturing all build logs for troubleshooting.

        Args:
            path: Build context path (directory containing Dockerfile)
            image_tag: Image tag in format 'name:version' (e.g., 'myapp:latest')
            dockerfile: Dockerfile name relative to path (default: Dockerfile)
            build_args: Optional build arguments as key-value pairs

        Returns:
            Dictionary containing:
                - image_id: Docker image ID (sha256:...)
                - image_tag: Full image tag
                - build_logs: List of build log lines
                - build_time: Build duration in seconds
                - size_bytes: Image size in bytes
        """
        try:
            start_time = datetime.utcnow()

            logger.info(
                "build_image_started",
                image_tag=image_tag,
                path=path,
                dockerfile=dockerfile
            )

            # Validate inputs
            validated_tag = validate_image_tag(image_tag)
            build_path = Path(path)

            if not build_path.exists():
                raise ValidationError(
                    f"Build path does not exist: {path}",
                    context={"path": path}
                )

            # Validate Dockerfile exists
            dockerfile_path = validate_dockerfile_path(dockerfile, build_path)

            # Get Docker client
            client = get_docker_client()

            # Build image
            image, build_logs = build_docker_image(
                client=client,
                path=str(build_path),
                tag=validated_tag,
                dockerfile=dockerfile,
                buildargs=build_args
            )

            # Calculate build time
            end_time = datetime.utcnow()
            build_time = (end_time - start_time).total_seconds()

            # Get image size
            image.reload()  # Refresh image metadata
            size_bytes = image.attrs.get('Size', 0)

            result = {
                "image_id": image.id,
                "image_tag": validated_tag,
                "build_logs": build_logs,
                "build_time": round(build_time, 2),
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2)
            }

            logger.info(
                "build_image_completed",
                image_id=image.id,
                tag=validated_tag,
                build_time=build_time
            )

            return result

        except (BuildError, ValidationError, DockerOperationError) as e:
            logger.error(
                "build_image_failed",
                image_tag=image_tag,
                path=path,
                error=str(e),
                context=getattr(e, 'context', {})
            )
            raise


    @mcp.tool()
    async def deploy_container(
        image_tag: str,
        container_name: str,
        host_port: Optional[int] = None,
        container_port: int = 8000,
        env_vars: Optional[Dict[str, str]] = None,
        repo_url: Optional[str] = None,
        branch: Optional[str] = None,
        commit_sha: Optional[str] = None,
        project_type: Optional[str] = None,
        deployment_id: Optional[str] = None
    ) -> dict:
        """
        Deploy Docker container with port conflict resolution.

        Deploys a container from the specified image with automatic port
        conflict detection and resolution. Implements security best practices:
        localhost-only binding, non-root user, memory limits.

        Args:
            image_tag: Docker image to deploy (e.g., 'myapp:v1.0')
            container_name: Unique container name (alphanumeric, hyphens, underscores)
            host_port: Host port to bind to (if None, auto-assigns from available range)
            container_port: Container internal port (default: 8000)
            env_vars: Optional environment variables as key-value pairs
            repo_url: Git repository URL (used for state tracking and rollback)
            branch: Git branch or ref that was deployed
            commit_sha: Full commit SHA of the deployed code
            project_type: Detected project type (docker, docker-compose, etc.)
            deployment_id: Optional custom deployment ID (auto-generated if not provided)

        Returns:
            Dictionary containing:
                - deployment_id: Deployment record ID (for rollback/tracking)
                - container_id: Docker container ID
                - container_name: Container name
                - host_port: Assigned host port
                - container_port: Container internal port
                - url: Access URL (http://localhost:PORT)
                - status: Container status
        """
        try:
            logger.info(
                "deploy_container_started",
                image_tag=image_tag,
                container_name=container_name,
                host_port=host_port
            )

            # Validate inputs
            validated_tag = validate_image_tag(image_tag)
            validated_name = validate_container_name(container_name)
            validated_container_port = validate_port(container_port, min_port=1)

            # Determine host port
            if host_port is None:
                # Auto-assign from available range
                assigned_port = find_available_port(
                    settings.port_range_start,
                    settings.port_range_end
                )
                logger.info("auto_assigned_port", port=assigned_port)
            else:
                # Use specified port (validate availability)
                assigned_port = validate_port(host_port, min_port=1024)

                if not is_port_available(assigned_port):
                    raise PortConflictError(
                        f"Port {assigned_port} is already in use",
                        context={"port": assigned_port}
                    )

            # Get Docker client
            client = get_docker_client()

            # Deploy container
            container = deploy_container_util(
                client=client,
                image_tag=validated_tag,
                container_name=validated_name,
                host_port=assigned_port,
                container_port=validated_container_port,
                env_vars=env_vars
            )

            # Refresh container status
            container.reload()

            # Persist deployment record for rollback and audit trail
            now = datetime.utcnow()
            dep_id = deployment_id or f"dep-{now.strftime('%Y%m%d%H%M%S')}-{validated_name}"
            image_name = validated_tag.split(":")[0]

            record = DeploymentRecord(
                deployment_id=dep_id,
                repo_url=repo_url or "unknown",
                branch=branch or "unknown",
                commit_sha=commit_sha or "unknown",
                project_type=project_type or "docker",
                image_name=image_name,
                image_tag=validated_tag,
                container_name=validated_name,
                container_id=container.id,
                host_port=assigned_port,
                container_port=validated_container_port,
                status=DeploymentStatus.RUNNING,
                created_at=now,
                started_at=now,
                completed_at=now,
            )
            state_manager = StateManager(settings.deployment_dir)
            state_manager.save(record)

            result = {
                "deployment_id": dep_id,
                "container_id": container.id,
                "container_name": validated_name,
                "host_port": assigned_port,
                "container_port": validated_container_port,
                "url": f"http://localhost:{assigned_port}",
                "status": container.status
            }

            logger.info(
                "deploy_container_completed",
                deployment_id=dep_id,
                container_id=container.id,
                container_name=validated_name,
                url=result["url"]
            )

            return result

        except (ContainerStartError, PortConflictError, ValidationError, DockerOperationError) as e:
            logger.error(
                "deploy_container_failed",
                image_tag=image_tag,
                container_name=container_name,
                error=str(e),
                context=getattr(e, 'context', {})
            )
            raise


    @mcp.tool()
    async def get_logs(
        container_name: str,
        tail: int = 100
    ) -> dict:
        """
        Retrieve container logs for debugging.

        Fetches the most recent log lines from a running or stopped container.
        Useful for troubleshooting deployment issues.

        Args:
            container_name: Container name to get logs from
            tail: Number of log lines to retrieve (default: 100, max: 1000)

        Returns:
            Dictionary containing:
                - container_name: Container name
                - logs: Log content as string (with timestamps)
                - lines_returned: Number of log lines returned
        """
        try:
            logger.info(
                "get_logs_started",
                container_name=container_name,
                tail=tail
            )

            # Validate inputs
            validated_name = validate_container_name(container_name)

            # Limit tail to prevent excessive memory usage
            tail = min(max(1, tail), 1000)

            # Get Docker client
            client = get_docker_client()

            # Get logs
            logs = get_container_logs(client, validated_name, tail=tail)

            # Count lines
            lines_count = len(logs.splitlines())

            result = {
                "container_name": validated_name,
                "logs": logs,
                "lines_returned": lines_count
            }

            logger.info(
                "get_logs_completed",
                container_name=validated_name,
                lines=lines_count
            )

            return result

        except (ValidationError, DockerOperationError) as e:
            logger.error(
                "get_logs_failed",
                container_name=container_name,
                error=str(e),
                context=getattr(e, 'context', {})
            )
            raise
