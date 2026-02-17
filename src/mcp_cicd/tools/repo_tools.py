# Este archivo implementa las herramientas MCP para operaciones de repositorio Git:
# clonado, checkout y detección de tipo de proyecto (Dockerfile vs docker-compose).

"""
MCP tools for Git repository operations.

Implements prepare_repo and detect_project_type tools.
"""
from pathlib import Path  # Manejo moderno de rutas de archivos
from typing import Optional  # Type hints para valores opcionales

from mcp.server.fastmcp import FastMCP  # Framework FastMCP para registro de herramientas

from ..config.settings import get_settings  # Singleton de configuración
from ..utils.git_utils import prepare_repository, WorkspaceManager  # Funciones de clonado y gestión de workspace
from ..utils.logging import get_logger  # Logger estructurado
from ..exceptions import GitOperationError  # Excepciones personalizadas

logger = get_logger(__name__)
settings = get_settings()


def register_repo_tools(mcp: FastMCP) -> None:
    """
    Register repository-related MCP tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    async def prepare_repo(
        repo_url: str,
        branch: str = "main",
        target_dir: Optional[str] = None
    ) -> dict:
        """
        Clone or update a Git repository for deployment.

        This tool handles repository preparation by cloning from the specified URL,
        checking out the requested branch/tag/commit, and extracting commit metadata.

        Args:
            repo_url: Git repository URL (HTTPS format, e.g., https://github.com/user/repo.git)
            branch: Branch name, tag, or commit SHA to checkout (default: main)
            target_dir: Optional custom workspace path (default: auto-generated from commit SHA)

        Returns:
            Dictionary containing:
                - workspace_path: Local path where repository was cloned
                - commit_sha: Full commit SHA (40 chars)
                - short_sha: Short commit SHA (7 chars)
                - branch: Branch name or "detached" if not on a branch
                - author: Commit author name
                - message: Commit message
                - timestamp: Commit timestamp (ISO format)
        """
        try:
            logger.info(
                "prepare_repo_started",
                repo_url=repo_url,
                branch=branch
            )

            # Initialize workspace manager
            workspace_manager = WorkspaceManager(settings.workspace_dir)

            # Prepare repository
            workspace_path, metadata = prepare_repository(
                repo_url=repo_url,
                workspace_manager=workspace_manager,
                branch=branch,
                allowed_hosts=settings.allowed_git_hosts
            )

            result = {
                "workspace_path": str(workspace_path),
                "commit_sha": metadata.full_sha,
                "short_sha": metadata.short_sha,
                "branch": metadata.branch,
                "author": metadata.author,
                "message": metadata.message,
                "timestamp": metadata.timestamp.isoformat()
            }

            logger.info(
                "prepare_repo_completed",
                workspace=str(workspace_path),
                commit=metadata.short_sha
            )

            return result

        except GitOperationError as e:
            logger.error(
                "prepare_repo_failed",
                repo_url=repo_url,
                error=str(e),
                context=e.context
            )
            raise


    @mcp.tool()
    async def detect_project_type(repo_path: str) -> dict:
        """
        Detect build system and framework from repository file markers.

        Analyzes the repository structure to determine the project type and
        extract relevant configuration details.

        Detection priority:
        1. docker-compose.yml/docker-compose.yaml/compose.yml → docker-compose
        2. Dockerfile → docker
        3. package.json → nodejs
        4. requirements.txt/pyproject.toml/setup.py → python
        5. go.mod → go
        6. Cargo.toml → rust

        Args:
            repo_path: Filesystem path to the cloned repository

        Returns:
            Dictionary containing:
                - project_type: Detected type (docker-compose, docker, nodejs, python, go, rust, unknown)
                - dockerfile_path: Path to Dockerfile if found (relative to repo root)
                - compose_file: Path to docker-compose file if found
                - exposed_ports: List of ports exposed in Dockerfile (if applicable)
                - details: Additional project-specific information
        """
        try:
            path = Path(repo_path)

            if not path.exists():
                raise GitOperationError(
                    f"Repository path does not exist: {repo_path}",
                    context={"path": repo_path}
                )

            logger.info("detecting_project_type", path=str(path))

            # Detection rules (priority order)
            detection_rules = [
                (["docker-compose.yml", "docker-compose.yaml", "compose.yml"], "docker-compose"),
                (["Dockerfile"], "docker"),
                (["package.json"], "nodejs"),
                (["requirements.txt", "pyproject.toml", "setup.py"], "python"),
                (["go.mod"], "go"),
                (["Cargo.toml"], "rust"),
            ]

            project_type = "unknown"
            dockerfile_path = None
            compose_file = None
            exposed_ports = []

            # Check each detection rule
            for markers, ptype in detection_rules:
                for marker in markers:
                    marker_path = path / marker
                    if marker_path.exists():
                        project_type = ptype

                        if ptype == "docker-compose":
                            compose_file = marker
                        elif ptype == "docker":
                            dockerfile_path = marker
                            # Parse exposed ports from Dockerfile
                            exposed_ports = _parse_dockerfile_ports(marker_path)

                        break

                if project_type != "unknown":
                    break

            result = {
                "project_type": project_type,
                "dockerfile_path": dockerfile_path,
                "compose_file": compose_file,
                "exposed_ports": exposed_ports,
                "details": {
                    "has_docker": (path / "Dockerfile").exists(),
                    "has_compose": any((path / f).exists() for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yml"])
                }
            }

            logger.info(
                "project_type_detected",
                type=project_type,
                path=str(path)
            )

            return result

        except Exception as e:
            logger.error(
                "detect_project_type_failed",
                path=repo_path,
                error=str(e)
            )
            raise


def _parse_dockerfile_ports(dockerfile_path: Path) -> list[int]:
    """
    Parse EXPOSE directives from Dockerfile.

    Args:
        dockerfile_path: Path to Dockerfile

    Returns:
        List of exposed port numbers
    """
    ports = []

    try:
        content = dockerfile_path.read_text()

        for line in content.splitlines():
            line = line.strip().upper()

            if line.startswith("EXPOSE"):
                # Extract port numbers (handle multiple ports and port/protocol format)
                parts = line.split()[1:]  # Skip "EXPOSE" keyword

                for part in parts:
                    # Handle "8080/tcp" format
                    port_str = part.split('/')[0]

                    try:
                        port = int(port_str)
                        ports.append(port)
                    except ValueError:
                        continue

    except Exception as e:
        logger.warning(
            "failed_to_parse_dockerfile_ports",
            dockerfile=str(dockerfile_path),
            error=str(e)
        )

    return ports
