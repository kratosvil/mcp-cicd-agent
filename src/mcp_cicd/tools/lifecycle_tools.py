# Este archivo implementa las herramientas MCP para gestión del ciclo de vida de deployments:
# detener contenedores y realizar rollbacks a versiones anteriores exitosas.

"""
MCP tools for deployment lifecycle management.

Implements stop_deployment and rollback tools.
"""
from datetime import datetime  # Manejo de fechas y timestamps
from typing import Optional  # Type hints para valores opcionales

from mcp.server.fastmcp import FastMCP  # Framework FastMCP para registro de herramientas

from ..config.settings import get_settings  # Singleton de configuración
from ..utils.docker_utils import (  # Funciones de Docker SDK
    get_docker_client,
    stop_and_remove_container,
    deploy_container as deploy_container_util
)
from ..utils.state_manager import StateManager  # Gestor de estado de deployments
from ..utils.validation import validate_container_name, validate_deployment_id  # Funciones de validación
from ..utils.logging import get_logger  # Logger estructurado
from ..exceptions import (  # Excepciones personalizadas
    DockerOperationError,
    RollbackError,
    ValidationError
)
from ..models.deployment import DeploymentRecord, DeploymentStatus  # Modelos y enums de deployment

logger = get_logger(__name__)
settings = get_settings()


def register_lifecycle_tools(mcp: FastMCP) -> None:
    """
    Register lifecycle management MCP tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    async def stop_deployment(container_name: str) -> dict:
        """
        Stop and remove a running deployment container.

        Gracefully stops the container (10 second timeout) and removes it
        from the Docker daemon. Does not remove the image.

        Args:
            container_name: Name of the container to stop

        Returns:
            Dictionary containing:
                - container_name: Container that was stopped
                - status: Operation status (stopped)
                - message: Human-readable message
        """
        try:
            logger.info(
                "stop_deployment_started",
                container_name=container_name
            )

            # Validate input
            validated_name = validate_container_name(container_name)

            # Get Docker client
            client = get_docker_client()

            # Stop and remove container
            stop_and_remove_container(client, validated_name)

            result = {
                "container_name": validated_name,
                "status": "stopped",
                "message": f"Container {validated_name} stopped and removed successfully"
            }

            logger.info(
                "stop_deployment_completed",
                container_name=validated_name
            )

            return result

        except (ValidationError, DockerOperationError) as e:
            logger.error(
                "stop_deployment_failed",
                container_name=container_name,
                error=str(e),
                context=getattr(e, 'context', {})
            )
            raise


    @mcp.tool()
    async def rollback(
        deployment_id: Optional[str] = None,
        repo_url: Optional[str] = None
    ) -> dict:
        """
        Rollback to the previous successful deployment.

        Finds the last successful deployment for the specified repository,
        stops the current failed deployment, and redeploys the previous
        working version on the same port.

        Rollback strategy follows AWS CodeDeploy pattern: creates a NEW
        deployment record (not a state revert) to maintain audit trail.

        Args:
            deployment_id: ID of the failed deployment to rollback from
            repo_url: Repository URL (alternative to deployment_id)

        Returns:
            Dictionary containing:
                - rollback_deployment_id: New deployment ID created for rollback
                - original_deployment_id: The failed deployment that was rolled back
                - previous_deployment_id: The successful deployment that was restored
                - container_name: New container name
                - host_port: Port where service is running
                - url: Access URL
                - commit_sha: Commit SHA of the rolled-back version
                - message: Human-readable message
        """
        try:
            logger.info(
                "rollback_started",
                deployment_id=deployment_id,
                repo_url=repo_url
            )

            # Validate that at least one identifier is provided
            if not deployment_id and not repo_url:
                raise ValidationError(
                    "Must provide either deployment_id or repo_url",
                    context={}
                )

            # Initialize state manager
            state_manager = StateManager(settings.deployment_dir)

            # Load failed deployment
            if deployment_id:
                validated_id = validate_deployment_id(deployment_id)
                failed_deployment = state_manager.load(validated_id)

                if not failed_deployment:
                    raise RollbackError(
                        f"Deployment {validated_id} not found",
                        context={"deployment_id": validated_id}
                    )

                target_repo_url = failed_deployment.repo_url
                exclude_id = validated_id
            else:
                target_repo_url = repo_url
                exclude_id = None

            # Find last successful deployment
            previous_deployment = state_manager.find_latest_successful(
                repo_url=target_repo_url,
                exclude=exclude_id
            )

            if not previous_deployment:
                raise RollbackError(
                    f"No previous successful deployment found for {target_repo_url}",
                    context={"repo_url": target_repo_url}
                )

            logger.info(
                "rollback_target_found",
                previous_deployment_id=previous_deployment.deployment_id,
                commit_sha=previous_deployment.commit_sha[:7]
            )

            # Get Docker client
            client = get_docker_client()

            # Stop current failed container if exists
            if deployment_id and failed_deployment.container_name:
                try:
                    stop_and_remove_container(client, failed_deployment.container_name)
                    logger.info(
                        "failed_container_stopped",
                        container=failed_deployment.container_name
                    )
                except DockerOperationError as e:
                    logger.warning(
                        "failed_to_stop_container",
                        container=failed_deployment.container_name,
                        error=str(e)
                    )

            # Generate new rollback deployment ID
            prev_short_sha = previous_deployment.commit_sha[:7]
            rollback_id = f"dep-{datetime.utcnow().strftime('%Y%m%d')}-rollback-{prev_short_sha}"

            # Create new container name for rollback
            rollback_container_name = f"{previous_deployment.image_name}-rollback-{prev_short_sha}-p{failed_deployment.host_port if deployment_id else previous_deployment.host_port}"

            # Redeploy previous image
            rollback_host_port = failed_deployment.host_port if deployment_id else previous_deployment.host_port
            container = deploy_container_util(
                client=client,
                image_tag=previous_deployment.image_tag,
                container_name=rollback_container_name,
                host_port=rollback_host_port,
                container_port=previous_deployment.container_port
            )

            # Persist rollback deployment record
            now = datetime.utcnow()
            rollback_record = DeploymentRecord(
                deployment_id=rollback_id,
                repo_url=target_repo_url,
                branch=previous_deployment.branch,
                commit_sha=previous_deployment.commit_sha,
                project_type=previous_deployment.project_type,
                image_name=previous_deployment.image_name,
                image_tag=previous_deployment.image_tag,
                container_name=rollback_container_name,
                container_id=container.id,
                host_port=rollback_host_port,
                container_port=previous_deployment.container_port,
                status=DeploymentStatus.RUNNING,
                created_at=now,
                started_at=now,
                completed_at=now,
                rollback_from=deployment_id,
            )
            state_manager.save(rollback_record)

            result = {
                "rollback_deployment_id": rollback_id,
                "original_deployment_id": deployment_id,
                "previous_deployment_id": previous_deployment.deployment_id,
                "container_name": rollback_container_name,
                "container_id": container.id,
                "host_port": rollback_host_port,
                "url": f"http://localhost:{rollback_host_port}",
                "commit_sha": previous_deployment.commit_sha,
                "short_sha": previous_deployment.commit_sha[:7],
                "message": f"Rolled back to deployment {previous_deployment.deployment_id} (commit {previous_deployment.commit_sha[:7]})"
            }

            logger.info(
                "rollback_completed",
                rollback_deployment_id=rollback_id,
                previous_deployment_id=previous_deployment.deployment_id,
                commit_sha=previous_deployment.commit_sha[:7]
            )

            return result

        except (RollbackError, ValidationError, DockerOperationError) as e:
            logger.error(
                "rollback_failed",
                deployment_id=deployment_id,
                repo_url=repo_url,
                error=str(e),
                context=getattr(e, 'context', {})
            )
            raise
